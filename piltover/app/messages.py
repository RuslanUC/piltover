from collections import defaultdict
from datetime import datetime, UTC
from time import time

from loguru import logger
from tortoise.expressions import Q
from tortoise.queryset import QuerySet

from piltover.app.account import username_regex_no_len
from piltover.app.updates import get_state_internal
from piltover.app.utils.updates_manager import UpdatesManager
from piltover.app.utils.utils import upload_file, resize_photo, generate_stripped
from piltover.db.enums import MediaType, PeerType
from piltover.db.models import User, Dialog, MessageDraft, ReadState, State, Peer, MessageMedia
from piltover.db.models.message import Message
from piltover.enums import ReqHandlerFlags
from piltover.exceptions import ErrorRpc
from piltover.high_level import MessageHandler, Client
from piltover.session_manager import SessionManager
from piltover.tl import WebPageEmpty, AttachMenuBots, DefaultHistoryTTL, Updates, InputPeerUser, InputPeerSelf, \
    EmojiKeywordsDifference, DocumentEmpty, InputDialogPeer, InputMediaUploadedDocument, PeerSettings, \
    UpdateDraftMessage, InputMediaUploadedPhoto, UpdateUserTyping, InputStickerSetAnimatedEmoji, StickerSet, \
    InputMessagesFilterEmpty, TLObject, InputMessagesFilterPinned, User as TLUser
from piltover.tl.functions.messages import GetDialogFilters, GetAvailableReactions, SetTyping, GetPeerSettings, \
    GetScheduledHistory, GetEmojiKeywordsLanguages, GetPeerDialogs, GetHistory, GetWebPage, SendMessage, ReadHistory, \
    GetStickerSet, GetRecentReactions, GetTopReactions, GetDialogs, GetAttachMenuBots, GetPinnedDialogs, \
    ReorderPinnedDialogs, GetStickers, GetSearchCounters, Search, GetSearchResultsPositions, GetDefaultHistoryTTL, \
    GetSuggestedDialogFilters, GetFeaturedStickers, GetFeaturedEmojiStickers, GetAllDrafts, SearchGlobal, \
    GetFavedStickers, GetCustomEmojiDocuments, GetMessagesReactions, GetArchivedStickers, GetEmojiStickers, \
    GetEmojiKeywords, DeleteMessages, GetWebPagePreview, EditMessage, SendMedia, GetMessageEditData, SaveDraft, \
    SendMessage_148, SendMedia_148, EditMessage_136, GetQuickReplies, GetDefaultTagReactions, GetSavedDialogs, \
    GetSavedReactionTags, ToggleDialogPin, UpdatePinnedMessage
from piltover.tl.types.messages import AvailableReactions, PeerSettings as MessagesPeerSettings, Messages, \
    PeerDialogs, AffectedMessages, Reactions, Dialogs, Stickers, SearchResultsPositions, SearchCounter, AllStickers, \
    FavedStickers, ArchivedStickers, FeaturedStickers, MessageEditData, StickerSet as messages_StickerSet, QuickReplies, \
    SavedDialogs, SavedReactionTags
from piltover.utils.snowflake import Snowflake

handler = MessageHandler("messages")


@handler.on_request(GetDialogFilters)
async def get_dialog_filters():
    return []


@handler.on_request(GetAvailableReactions)
async def get_available_reactions():
    return AvailableReactions(hash=0, reactions=[])


@handler.on_request(SetTyping, ReqHandlerFlags.AUTH_REQUIRED)
async def set_typing(request: SetTyping, user: User):
    if (peer := await Peer.from_input_peer(user, request.peer)) is None:
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    if peer.type == PeerType.SELF:
        return True

    other = peer.user
    updates = Updates(
        updates=[UpdateUserTyping(user_id=user.id, action=request.action)],
        users=[await user.to_tl(other)],
        chats=[],
        date=int(time()),
        seq=0,
    )
    await SessionManager().send(updates, other.id)

    return True


@handler.on_request(GetPeerSettings)
async def get_peer_settings():
    return MessagesPeerSettings(
        settings=PeerSettings(),
        chats=[],
        users=[],
    )


@handler.on_request(GetScheduledHistory)
async def get_scheduled_history():
    return Messages(messages=[], chats=[], users=[])


@handler.on_request(GetEmojiKeywordsLanguages)
async def get_emoji_keywords_languages():
    return []


def _get_messages_query(
        peer: Peer | User, max_id: int, min_id: int, offset_id: int, limit: int, add_offset: int,
        from_user_id: int | None = None, min_date: int | None = None, max_date: int | None = None, q: str | None = None,
        filter_: TLObject | None = None
) -> QuerySet[Message]:
    query = Q(peer=peer) if isinstance(peer, Peer) else Q(peer__owner=peer)

    if q:
        query &= Q(message__istartswith=q)

    if from_user_id:
        query &= Q(author__id=from_user_id)

    if min_date:
        query &= Q(date__gt=datetime.fromtimestamp(min_date, UTC))
    if max_date:
        query &= Q(date__lt=datetime.fromtimestamp(max_date, UTC))

    if max_id:
        query &= Q(id__lte=max_id)
    if min_id:
        query &= Q(id__gte=min_id)

    if offset_id:
        query &= Q(id__gt=offset_id)

    if isinstance(filter_, InputMessagesFilterPinned):
        query &= Q(pinned=True)
    elif filter_ is not None and not isinstance(filter_, InputMessagesFilterEmpty):
        logger.warning(f"Unsupported filter: {filter_}")
        query = Q(id=0)

    limit = max(min(100, limit), 1)
    return Message.filter(query).limit(limit).offset(add_offset).order_by("-date")\
        .select_related("author", "peer", "peer__user")

async def get_messages_internal(
        peer: Peer | User, max_id: int, min_id: int, offset_id: int, limit: int, add_offset: int,
        from_user_id: int | None = None, min_date: int | None = None, max_date: int | None = None, q: str | None = None,
        filter_: TLObject | None = None
) -> list[Message]:
    return await _get_messages_query(
        peer, max_id, min_id, offset_id, limit, add_offset, from_user_id, min_date, max_date, q, filter_,
    )


async def _format_messages(user: User, messages: list[Message], users: dict[int, TLUser] | None = None) -> Messages:
    if users is None:
        users = {}

    messages_tl = []
    for message in messages:
        messages_tl.append(await message.to_tl(user))

        if message.author.id not in users:
            users[message.author.id] = await message.author.to_tl(user)
        if message.peer.user is not None and message.peer.user.id not in users:
            users[message.peer.user.id] = await message.peer.user.to_tl(user)

    # TODO: MessagesSlice
    return Messages(
        messages=messages_tl,
        chats=[],
        users=list(users.values()),
    )


@handler.on_request(GetHistory, ReqHandlerFlags.AUTH_REQUIRED)
async def get_history(request: GetHistory, user: User) -> Messages:
    if (peer := await Peer.from_input_peer(user, request.peer)) is None:
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    messages = await get_messages_internal(
        peer, request.max_id, request.min_id, request.offset_id, request.limit, request.add_offset
    )
    if not messages:
        return Messages(messages=[], chats=[], users=[])

    return await _format_messages(user, messages)


async def _send_message_internal(
        user: User, peer: Peer, reply_to_message_id: int | None, clear_draft: bool, author: User, **message_kwargs
) -> Updates:
    reply = await Message.get_or_none(id=reply_to_message_id, peer=peer) if reply_to_message_id else None

    peers = [peer]
    peers.extend(await peer.get_opposite())
    messages: dict[Peer, Message] = {}

    internal_id = Snowflake.make_id()
    for to_peer in peers:
        await Dialog.get_or_create(peer=to_peer)
        messages[to_peer] = await Message.create(
            internal_id=internal_id,
            peer=to_peer,
            reply_to=(await Message.get_or_none(peer=to_peer, internal_id=reply.internal_id)) if reply else None,
            author=author,
            **message_kwargs
        )

    # TODO: rewrite when pypika fixes delete with join for mysql
    # Not doing await MessageDraft.filter(...).delete()
    # Because pypika generates sql for MySql/MariaDB like "DELETE FROM `messagedraft` LEFT OUTER JOIN"
    # But `messagedraft` must also be placed between "DELETE" and "FROM", like this:
    # "DELETE `messagedraft` FROM `messagedraft` LEFT OUTER JOIN"
    if clear_draft and (draft := await MessageDraft.get_or_none(dialog__peer=peer)) is not None:
        await draft.delete()
        await UpdatesManager.update_draft(user, peer, None)

    if (upd := await UpdatesManager.send_message(user, messages, bool(message_kwargs.get("media")))) is None:
        assert False, "unknown chat type ?"

    return upd


@handler.on_request(SendMessage_148, ReqHandlerFlags.AUTH_REQUIRED)
@handler.on_request(SendMessage, ReqHandlerFlags.AUTH_REQUIRED)
async def send_message(request: SendMessage, user: User):
    if (peer := await Peer.from_input_peer(user, request.peer)) is None:
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    if not request.message:
        raise ErrorRpc(error_code=400, error_message="MESSAGE_EMPTY")
    if len(request.message) > 2000:
        raise ErrorRpc(error_code=400, error_message="MESSAGE_TOO_LONG")

    reply_to_message_id = None
    if isinstance(request, SendMessage) and request.reply_to is not None:
        reply_to_message_id = request.reply_to.reply_to_msg_id
    elif isinstance(request, SendMessage_148) and request.reply_to_msg_id is not None:
        reply_to_message_id = request.reply_to_msg_id

    return await _send_message_internal(
        user, peer, reply_to_message_id, request.clear_draft,
        author=user, message=request.message,
    )


@handler.on_request(ReadHistory, ReqHandlerFlags.AUTH_REQUIRED)
async def read_history(request: ReadHistory, user: User):
    if (peer := await Peer.from_input_peer(user, request.peer)) is None:
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    ex = await ReadState.get_or_none(dialog__peer=peer)
    message = await Message.filter(
        id__lte=min(request.max_id, ex.last_message_id if ex is not None else request.max_id), peer=peer,
    ).order_by("-id").limit(1)
    messages_count = await Message.filter(
        id__gt=ex.last_message_id if ex is not None else 0, id__lt=message[0].id, peer=peer,
    ).count()

    # TODO: save to database
    return AffectedMessages(
        pts=await State.add_pts(user, messages_count),
        pts_count=messages_count,
    )


@handler.on_request(GetWebPage)
async def get_web_page():
    return WebPageEmpty(id=0)


@handler.on_request(GetStickerSet)
async def get_sticker_set(request: GetStickerSet):
    if isinstance(request.stickerset, InputStickerSetAnimatedEmoji):
        return messages_StickerSet(
            set=StickerSet(
                id=1,
                access_hash=1,
                title="AnimatedEmoji",
                short_name="animated_emoji",
                count=0,
                hash=1,
                official=True,
                emojis=True,
            ),
            packs=[],
            keywords=[],
            documents=[]
        )

    raise ErrorRpc(error_code=406, error_message="STICKERSET_INVALID")


@handler.on_request(GetTopReactions)
async def get_top_reactions():
    return Reactions(hash=0, reactions=[])


@handler.on_request(GetRecentReactions)
async def get_recent_reactions():
    return Reactions(hash=0, reactions=[])


async def format_dialogs(user: User, dialogs: list[Dialog]) -> dict[str, list]:
    messages = []
    users = {}
    for dialog in dialogs:
        message = await Message.filter(peer=dialog.peer).select_related("author", "peer").order_by("-id").first()
        if message is not None:
            messages.append(await message.to_tl(user))
            if message.author.id not in users:
                users[message.author.id] = await message.author.to_tl(user)

        if dialog.peer.peer_user(user) is not None and dialog.peer.peer_user(user).id not in users:
            users[dialog.peer.user.id] = await dialog.peer.peer_user(user).to_tl(user)

    return {
        "dialogs": [await dialog.to_tl() for dialog in dialogs],
        "messages": messages,
        "chats": [],
        "users": list(users.values()),
    }


# noinspection PyUnusedLocal
async def get_dialogs_internal(
        peers: list[InputDialogPeer] | None, user: User, offset_id: int = 0, offset_date: int = 0, limit: int = 100
) -> dict:
    query = Q(peer__owner=user)
    if offset_id:
        query &= Q(peer__messages__id__gt=offset_id)
    if offset_date:
        query &= Q(peer__messages__date__gt=datetime.fromtimestamp(offset_date, UTC))

    if peers:
        peers_query = None
        for peer in peers:
            if isinstance(peer.peer, InputPeerSelf):
                add_to_query = Q(peer__type=PeerType.SELF, peer__user=None)
            elif isinstance(peer.peer, InputPeerUser):
                add_to_query = Q(
                    peer__type=PeerType.USER, peer__user__id=peer.peer.user_id, peer__access_hash=peer.peer.access_hash,
                )
            else:
                continue

            peers_query = add_to_query if peers_query is None else peers_query | add_to_query

        if peers_query is not None:
            query &= peers_query

    if limit > 100 or limit < 1:
        limit = 100

    dialogs = await Dialog.filter(query).select_related(
        "peer", "peer__owner", "peer__user"
    ).order_by("-peer__messages__date").limit(limit).all()

    return await format_dialogs(user, dialogs)


@handler.on_request(GetDialogs, ReqHandlerFlags.AUTH_REQUIRED)
async def get_dialogs(request: GetDialogs, user: User):
    return Dialogs(**(
        await get_dialogs_internal(None, user, request.offset_id, request.offset_date, request.limit)
    ))


@handler.on_request(GetPeerDialogs, ReqHandlerFlags.AUTH_REQUIRED)
async def get_peer_dialogs(client: Client, request: GetPeerDialogs, user: User):
    return PeerDialogs(
        **(await get_dialogs_internal(request.peers, user)),
        state=await get_state_internal(client, user)
    )


@handler.on_request(GetAttachMenuBots)
async def get_attach_menu_bots():
    return AttachMenuBots(
        hash=0,
        bots=[],
        users=[],
    )


@handler.on_request(GetPinnedDialogs, ReqHandlerFlags.AUTH_REQUIRED)
async def get_pinned_dialogs(client: Client, user: User):
    dialogs = await Dialog.filter(peer__owner=user, pinned_index__not_isnull=True)\
        .select_related("peer", "peer__user").order_by("-pinned_index")

    return PeerDialogs(
        **(await format_dialogs(user, dialogs)),
        state=await get_state_internal(client, user)
    )


@handler.on_request(ToggleDialogPin, ReqHandlerFlags.AUTH_REQUIRED)
async def toggle_dialog_pin(request: ToggleDialogPin, user: User):
    if (peer := await Peer.from_input_peer(user, request.peer.peer)) is None \
            or (dialog := await Dialog.get_or_none(peer=peer)) is None:
        raise ErrorRpc(error_code=400, error_message="PEER_HISTORY_EMPTY")

    if dialog.pinned_index:
        dialog.pinned_index = None
    else:
        dialog.pinned_index = await Dialog.filter(peer=peer, pinned_index__not_isnull=True).count()
        if dialog.pinned_index > 10:
            raise ErrorRpc(error_code=400, error_message="PINNED_DIALOGS_TOO_MUCH")

    await dialog.save(update_fields=["pinned_index"])
    await UpdatesManager.pin_dialog(user, peer)

    return True


@handler.on_request(ReorderPinnedDialogs, ReqHandlerFlags.AUTH_REQUIRED)
async def reorder_pinned_dialogs(request: ReorderPinnedDialogs, user: User):
    pinned_now = await Dialog.filter(peer__owner=user, pinned_index__not_isnull=True).select_related("peer")
    pinned_now = {dialog.peer: dialog for dialog in pinned_now}
    pinned_after = []
    to_unpin: dict = pinned_now.copy() if request.force else {}

    for dialog_peer in request.order:
        if (peer := await Peer.from_input_peer(user, dialog_peer.peer)) is None:
            continue

        dialog = pinned_now.get(peer, None) or await Dialog.get_or_none(peer=peer).select_related("peer")
        if not dialog:
            continue

        pinned_after.append(dialog)
        to_unpin.pop(peer, None)

    if not request.force:
        pinned_after.extend(sorted(pinned_now.values(), key=lambda d: d.pinned_index))

    if to_unpin:
        unpin_ids = [dialog.id for dialog in to_unpin.values()]
        await Dialog.filter(id__in=unpin_ids).update(pinned_index=None)

    pinned_after.reverse()
    for idx, dialog in enumerate(pinned_after):
        dialog.pinned_index = idx

    if pinned_after:
        await Dialog.bulk_update(pinned_after, fields=["pinned_index"])
    await UpdatesManager.reorder_pinned_dialogs(user, pinned_after)

    return True


@handler.on_request(GetStickers)
async def get_stickers():
    return Stickers(hash=0, stickers=[])


@handler.on_request(GetDefaultHistoryTTL)
async def get_default_history_ttl():
    return DefaultHistoryTTL(period=10)


@handler.on_request(GetSearchResultsPositions)
async def get_search_results_positions():
    return SearchResultsPositions(
        count=0,
        positions=[],
    )


@handler.on_request(Search, ReqHandlerFlags.AUTH_REQUIRED)
async def messages_search(request: Search, user: User) -> Messages:
    if (peer := await Peer.from_input_peer(user, request.peer)) is None:
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    from_user_id = None
    if isinstance(request.from_id, InputPeerUser):
        from_user_id = request.from_id.user_id
    elif isinstance(request.from_id, InputPeerSelf):
        from_user_id = user.id

    messages = await get_messages_internal(
        peer, request.max_id, request.min_id, request.offset_id, request.limit, request.add_offset, from_user_id,
        request.min_date, request.max_date, request.q, request.filter
    )

    return await _format_messages(user, messages)


@handler.on_request(GetSearchCounters, ReqHandlerFlags.AUTH_REQUIRED)
async def get_search_counters(request: GetSearchCounters, user: User):
    if (peer := await Peer.from_input_peer(user, request.peer)) is None:
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    return [
        SearchCounter(
            filter=filt,
            count=await _get_messages_query(peer, 0, 0, 0, 0, 0, 0, 0, 0, None, filt).count(),
        ) for filt in request.filters
    ]


@handler.on_request(GetSuggestedDialogFilters)
async def get_suggested_dialog_filters():
    return []


@handler.on_request(GetFeaturedStickers)
@handler.on_request(GetFeaturedEmojiStickers)
async def get_featured_stickers():
    return FeaturedStickers(
        hash=0,
        count=0,
        sets=[],
        unread=[],
    )


@handler.on_request(GetAllDrafts, ReqHandlerFlags.AUTH_REQUIRED)
async def get_all_drafts(user: User):
    users = {}
    updates = []
    drafts = await MessageDraft.filter(dialog__peer__owner=user).select_related("dialog", "dialog__peer", "dialog__peer__user")
    for draft in drafts:
        peer = draft.dialog.peer
        updates.append(UpdateDraftMessage(peer=peer.to_tl(), draft=draft.to_tl()))
        if peer.user.id not in users:
            users[peer.user.id] = await peer.user.to_tl(user)

    return Updates(
        updates=updates,
        users=list(users.values()),
        chats=[],
        date=int(time()),
        seq=0,
    )


@handler.on_request(GetFavedStickers)
async def get_faved_stickers():
    return FavedStickers(
        hash=0,
        packs=[],
        stickers=[],
    )


@handler.on_request(SearchGlobal, ReqHandlerFlags.AUTH_REQUIRED)
async def search_global(request: SearchGlobal, user: User):
    users = {}

    q = user_q = request.q
    if q.startswith("@"):
        user_q = q[1:]
    if username_regex_no_len.match(user_q):
        users = {
            oth_user.id: await oth_user.to_tl(user)
            for oth_user in await User.filter(username__istartswith=user_q).limit(10)
        }

    limit = max(min(request.limit, 1), 10)

    # TODO: offset_peer ?
    messages = await get_messages_internal(
        user, 0, 0, request.offset_id, limit, 0, 0,
        request.min_date, request.max_date, request.q, request.filter
    )

    return await _format_messages(user, messages, users)


@handler.on_request(GetCustomEmojiDocuments)
async def get_custom_emoji_documents(request: GetCustomEmojiDocuments):
    return [DocumentEmpty(id=doc) for doc in request.document_id]


@handler.on_request(GetMessagesReactions)
async def get_messages_reactions():
    return Updates(updates=[], users=[], chats=[], date=int(time()), seq=0)


@handler.on_request(GetArchivedStickers)
async def get_archived_stickers():
    return ArchivedStickers(count=0, sets=[])


@handler.on_request(GetEmojiStickers)
async def get_emoji_stickers(request: GetEmojiStickers):
    return AllStickers(hash=request.hash, sets=[])


@handler.on_request(GetEmojiKeywords)
async def get_emoji_keywords(request: GetEmojiKeywords):
    return EmojiKeywordsDifference(lang_code=request.lang_code, from_version=0, version=0, keywords=[])


@handler.on_request(DeleteMessages, ReqHandlerFlags.AUTH_REQUIRED)
async def delete_messages(request: DeleteMessages, user: User):
    ids = request.id[:100]
    messages = defaultdict(list)
    for message in await Message.filter(id__in=ids, peer__owner=user).select_related("peer", "peer__user", "peer__owner"):
        messages[user].append(message.id)
        if request.revoke:
            for opposite_peer in await message.peer.get_opposite():
                opp_message = await Message.get_or_none(internal_id=message.internal_id, peer=opposite_peer)
                if opp_message is not None:
                    messages[message.peer.user].append(opp_message.id)

    all_ids = [i for ids in messages.values() for i in ids]
    if not all_ids:
        updates_state, _ = await State.get_or_create(user=user)
        return AffectedMessages(pts=updates_state.pts, pts_count=0)

    await Message.filter(id__in=all_ids).delete()
    pts = await UpdatesManager.delete_messages(user, messages)
    return AffectedMessages(pts=pts, pts_count=len(all_ids))


@handler.on_request(GetWebPagePreview)
async def get_webpage_preview():
    return WebPageEmpty(id=0)


@handler.on_request(EditMessage_136, ReqHandlerFlags.AUTH_REQUIRED)
@handler.on_request(EditMessage, ReqHandlerFlags.AUTH_REQUIRED)
async def edit_message(request: EditMessage | EditMessage_136, user: User):
    if (peer := await Peer.from_input_peer(user, request.peer)) is None:
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    if (message := await Message.get_or_none(peer=peer, id=request.id).select_related("peer", "author")) is None:
        raise ErrorRpc(error_code=400, error_message="MESSAGE_ID_INVALID")

    if not request.message:
        raise ErrorRpc(error_code=400, error_message="MESSAGE_EMPTY")
    if message.author != user:
        raise ErrorRpc(error_code=403, error_message="MESSAGE_AUTHOR_REQUIRED")
    if message.message == request.message:
        raise ErrorRpc(error_code=400, error_message="MESSAGE_NOT_MODIFIED")

    peers = [peer]
    peers.extend(await peer.get_opposite())
    messages: dict[Peer, Message] = {}

    edit_date = datetime.now(UTC)
    for to_peer in peers:
        message = await Message.get_or_none(
            internal_id=message.internal_id, peer=to_peer,
        ).select_related("author", "peer")
        if message is not None:
            await message.update(message=request.message, edit_date=edit_date)
            messages[to_peer] = message

    return await UpdatesManager.edit_message(user, messages)


@handler.on_request(SendMedia_148, ReqHandlerFlags.AUTH_REQUIRED)
@handler.on_request(SendMedia, ReqHandlerFlags.AUTH_REQUIRED)
async def send_media(request: SendMedia | SendMedia_148, user: User):
    if (peer := await Peer.from_input_peer(user, request.peer)) is None:
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    if not isinstance(request.media, (InputMediaUploadedDocument, InputMediaUploadedPhoto)):
        raise ErrorRpc(error_code=400, error_message="MEDIA_INVALID")
    if len(request.message) > 2000:
        raise ErrorRpc(error_code=400, error_message="MEDIA_CAPTION_TOO_LONG")

    mime = request.media.mime_type if isinstance(request.media, InputMediaUploadedDocument) else "image/jpeg"
    attributes = request.media.attributes if isinstance(request.media, InputMediaUploadedDocument) else []
    media_type = MediaType.DOCUMENT if isinstance(request.media, InputMediaUploadedDocument) else MediaType.PHOTO

    file = await upload_file(user, request.media.file, mime, attributes)
    sizes = await resize_photo(str(file.physical_id)) if mime.startswith("image/") else []
    stripped = await generate_stripped(str(file.physical_id)) if mime.startswith("image/") else b""
    await file.update(attributes=file.attributes | {"_sizes": sizes, "_size_stripped": stripped.hex()})

    media = await MessageMedia.create(file=file, spoiler=request.media.spoiler, type=media_type)

    reply_to_message_id = None
    if isinstance(request, SendMessage) and request.reply_to is not None:
        reply_to_message_id = request.reply_to.reply_to_msg_id
    elif isinstance(request, SendMessage_148) and request.reply_to_msg_id is not None:
        reply_to_message_id = request.reply_to_msg_id

    return await _send_message_internal(
        user, peer, reply_to_message_id, request.clear_draft,
        author=user, message=request.message, media=media,
    )


@handler.on_request(GetMessageEditData, ReqHandlerFlags.AUTH_REQUIRED)
async def get_message_edit_data():
    return MessageEditData()


@handler.on_request(SaveDraft, ReqHandlerFlags.AUTH_REQUIRED)
async def save_draft(request: SaveDraft, user: User):
    if (peer := await Peer.from_input_peer(user, request.peer)) is None:
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    dialog = await Dialog.get_or_create(peer=peer)
    draft, _ = await MessageDraft.get_or_create(
        dialog=dialog,
        defaults={"message": request.message, "date": datetime.now()}
    )

    await UpdatesManager.update_draft(user, peer, draft)
    return True


@handler.on_request(GetQuickReplies, ReqHandlerFlags.AUTH_REQUIRED)
async def get_quick_replies() -> QuickReplies:
    return QuickReplies(
        quick_replies=[],
        messages=[],
        chats=[],
        users=[],
    )


@handler.on_request(GetDefaultTagReactions, ReqHandlerFlags.AUTH_REQUIRED)
async def get_default_tag_reactions() -> Reactions:
    return Reactions(
        hash=0,
        reactions=[],
    )


@handler.on_request(GetSavedDialogs, ReqHandlerFlags.AUTH_REQUIRED)
async def get_saved_dialogs() -> SavedDialogs:
    return SavedDialogs(
        dialogs=[],
        messages=[],
        chats=[],
        users=[],
    )


@handler.on_request(GetSavedReactionTags, ReqHandlerFlags.AUTH_REQUIRED)
async def get_saved_reaction_tags() -> SavedReactionTags:
    return SavedReactionTags(
        tags=[],
        hash=0,
    )


@handler.on_request(UpdatePinnedMessage, ReqHandlerFlags.AUTH_REQUIRED)
async def update_pinned_message(request: UpdatePinnedMessage, user: User):
    # TODO: request.silent (create service message)

    if (peer := await Peer.from_input_peer(user, request.peer)) is None:
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    if (message := await Message.get_or_none(id=request.id, peer=peer).select_related("peer", "author")) is None:
        raise ErrorRpc(error_code=400, error_message="MESSAGE_ID_INVALID")

    message.pinned = not request.unpin
    messages = {peer: message}

    if not request.pm_oneside:
        other_messages = await Message.filter(
            peer__user=user, internal_id=message.internal_id,
        ).select_related("peer", "author")
        for other_message in other_messages:
            other_message.pinned = message.pinned
            messages[other_message.peer] = other_message

    await Message.bulk_update(messages.values(), ["pinned"])

    result = await UpdatesManager.pin_message(user, messages)

    return result
