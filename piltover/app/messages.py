from collections import defaultdict
from datetime import datetime, UTC
from time import time

from tortoise.expressions import Subquery, Q

from piltover.app.account import username_regex_no_len
from piltover.app.updates import get_state_internal
from piltover.app.utils.to_tl import ToTL
from piltover.app.utils.updates_manager import UpdatesManager, UpdatesContext
from piltover.app.utils.utils import upload_file, resize_photo, generate_stripped
from piltover.db.enums import ChatType, MediaType
from piltover.db.models import User, Chat, Dialog, MessageMedia, MessageDraft, ReadState, State
from piltover.db.models.message import Message
from piltover.enums import ReqHandlerFlags
from piltover.exceptions import ErrorRpc
from piltover.high_level import MessageHandler, Client
from piltover.session_manager import SessionManager
from piltover.tl import WebPageEmpty, AttachMenuBots, DefaultHistoryTTL, Updates, InputPeerUser, \
    InputPeerSelf, EmojiKeywordsDifference, DocumentEmpty, \
    InputDialogPeer, UpdateEditMessage, InputMediaUploadedDocument, PeerSettings, UpdateDraftMessage, \
    InputMediaUploadedPhoto, UpdateUserTyping, DraftMessageEmpty, DraftMessage
from piltover.tl.functions.messages import GetDialogFilters, GetAvailableReactions, SetTyping, GetPeerSettings, \
    GetScheduledHistory, GetEmojiKeywordsLanguages, GetPeerDialogs, GetHistory, GetWebPage, SendMessage, ReadHistory, \
    GetStickerSet, GetRecentReactions, GetTopReactions, GetDialogs, GetAttachMenuBots, GetPinnedDialogs, \
    ReorderPinnedDialogs, GetStickers, GetSearchCounters, Search, GetSearchResultsPositions, GetDefaultHistoryTTL, \
    GetSuggestedDialogFilters, GetFeaturedStickers, GetFeaturedEmojiStickers, GetAllDrafts, SearchGlobal, \
    GetFavedStickers, GetCustomEmojiDocuments, GetMessagesReactions, GetArchivedStickers, GetEmojiStickers, \
    GetEmojiKeywords, DeleteMessages, GetWebPagePreview, EditMessage, SendMedia, GetMessageEditData, SaveDraft
from piltover.tl.types.messages import AvailableReactions, PeerSettings as MessagesPeerSettings, Messages, \
    PeerDialogs, AffectedMessages, \
    Reactions, Dialogs, Stickers, SearchResultsPositions, SearchCounter, AllStickers, \
    FavedStickers, ArchivedStickers, FeaturedStickers, MessageEditData

handler = MessageHandler("messages")


# noinspection PyUnusedLocal
@handler.on_request(GetDialogFilters)
async def get_dialog_filters(client: Client, request: GetDialogFilters):
    return []


# noinspection PyUnusedLocal
@handler.on_request(GetAvailableReactions)
async def get_available_reactions(client: Client, request: GetAvailableReactions):
    return AvailableReactions(hash=0, reactions=[])


# noinspection PyUnusedLocal
@handler.on_request(SetTyping, ReqHandlerFlags.AUTH_REQUIRED)
async def set_typing(client: Client, request: SetTyping, user: User):
    if (chat := await Chat.from_input_peer(user, request.peer, True)) is None:
        raise ErrorRpc(error_code=500, error_message="Failed to create chat")

    if chat.type != ChatType.PRIVATE:
        return True

    other = await chat.get_other_user(user)
    updates = Updates(
        updates=[UpdateUserTyping(user_id=user.id, action=request.action)],
        users=[await user.to_tl(other)],
        chats=[],
        date=int(time()),
        seq=0,
    )
    await SessionManager().send(updates, other.id)

    return True


# noinspection PyUnusedLocal
@handler.on_request(GetPeerSettings)
async def get_peer_settings(client: Client, request: GetPeerSettings):
    return MessagesPeerSettings(
        settings=PeerSettings(),
        chats=[],
        users=[],
    )


# noinspection PyUnusedLocal
@handler.on_request(GetScheduledHistory)
async def get_scheduled_history(client: Client, request: GetScheduledHistory):
    return Messages(messages=[], chats=[], users=[])


# noinspection PyUnusedLocal
@handler.on_request(GetEmojiKeywordsLanguages)
async def get_emoji_keywords_languages(client: Client, request: GetEmojiKeywordsLanguages):
    return []


# noinspection PyUnusedLocal
@handler.on_request(GetHistory, ReqHandlerFlags.AUTH_REQUIRED)
async def get_history(client: Client, request: GetHistory, user: User):
    if isinstance(request.peer, InputPeerSelf):
        chat = await Chat.get_private(user)
    elif isinstance(request.peer, InputPeerUser):
        if (to_user := await User.get_or_none(id=request.peer.user_id)) is None:
            raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")
        chat = await Chat.get_private(user, to_user)
    else:
        raise ErrorRpc(error_code=400, error_message="PEER_ID_NOT_SUPPORTED")

    if chat is None:
        return Messages(messages=[], chats=[], users=[])

    limit = request.limit
    if limit > 100 or limit < 1:
        limit = 100
    query = {}
    if request.max_id > 0:
        query["id__lte"] = request.max_id
    if request.min_id > 0:
        query["id__gte"] = request.min_id

    messages = await Message.filter(chat=chat, **query).select_related("author", "chat").limit(limit).all()
    if not messages:
        return Messages(messages=[], chats=[], users=[])

    users = {}
    for message in messages:
        if message.author.id in users:
            continue
        users[message.author.id] = await message.author.to_tl(user)

    return Messages(
        messages=[await message.to_tl(user) for message in messages],
        chats=[],
        users=list(users.values()),
    )


# noinspection PyUnusedLocal
@handler.on_request(SendMessage, ReqHandlerFlags.AUTH_REQUIRED)
async def send_message(client: Client, request: SendMessage, user: User):
    if (chat := await Chat.from_input_peer(user, request.peer, True)) is None:
        raise ErrorRpc(error_code=500, error_message="Failed to create chat")

    if not request.message:
        raise ErrorRpc(error_code=400, error_message="MESSAGE_EMPTY")
    if len(request.message) > 2000:
        raise ErrorRpc(error_code=400, error_message="MESSAGE_TOO_LONG")

    reply = None
    if request.reply_to is not None:
        reply = await Message.get_or_none(id=request.reply_to.reply_to_msg_id, chat=chat)

    message = await Message.create(message=request.message, author=user, chat=chat, reply_to=reply)
    await MessageDraft.filter(dialog__chat=chat, dialog__user=user).delete()
    await send_update_draft(user, chat, DraftMessageEmpty())

    if (upd := await UpdatesManager().send_message(user, message)) is None:
        assert False, "unknown chat type ?"

    return upd


# noinspection PyUnusedLocal
@handler.on_request(ReadHistory, ReqHandlerFlags.AUTH_REQUIRED)
async def read_history(client: Client, request: ReadHistory, user: User):
    if (chat := await Chat.from_input_peer(user, request.peer, True)) is None:
        raise ErrorRpc(error_code=500, error_message="Failed to create chat")
    ex = await ReadState.get_or_none(dialog__user=user, dialog__chat=chat)
    message = await Message.filter(
        id__lte=min(request.max_id, ex.last_message_id if ex is not None else request.max_id), chat=chat
    ).order_by("-id").limit(1)
    messages_count = await Message.filter(
        id__gt=ex.last_message_id if ex is not None else 0, id__lt=message[0].id, chat=chat
    ).count()
    return AffectedMessages(
        pts=3,
        pts_count=messages_count,
    )


# noinspection PyUnusedLocal
@handler.on_request(GetWebPage)
async def get_web_page(client: Client, request: GetWebPage):
    return WebPageEmpty(id=0)


# noinspection PyUnusedLocal
@handler.on_request(GetStickerSet)
async def get_sticker_set(client: Client, request: GetStickerSet):
    raise ErrorRpc(error_code=406, error_message="STICKERSET_INVALID")


# noinspection PyUnusedLocal
@handler.on_request(GetTopReactions)
async def get_top_reactions(client: Client, request: GetTopReactions):
    return Reactions(hash=0, reactions=[])


# noinspection PyUnusedLocal
@handler.on_request(GetRecentReactions)
async def get_recent_reactions(client: Client, request: GetRecentReactions):
    return Reactions(hash=0, reactions=[])


# noinspection PyUnusedLocal
async def get_dialogs_internal(peers: list[InputDialogPeer] | None, user: User, offset_id: int = 0,
                               offset_date: int = 0, limit: int = 100):
    # TODO: get dialogs by peers

    query = Q(user=user)
    if offset_id:
        query &= Q(chat__messages__id__gt=offset_id)
    if offset_date:
        query &= Q(chat__messages__date__gt=datetime.fromtimestamp(offset_date, UTC))

    if limit > 100 or limit < 1:
        limit = 100

    dialogs = await Dialog.filter(query).select_related("user", "chat").order_by("-chat__messages__date")\
        .limit(limit).all()
    messages = []
    users = {}
    for dialog in dialogs:
        if (message := await Message.filter(chat=dialog.chat).select_related("author", "chat").order_by("-id")
                .first()) is not None:
            messages.append(await message.to_tl(user))
        users_, _ = await dialog.chat.to_tl_users_chats(user, users)
        users.update(users_)

    return {
        "dialogs": [await dialog.to_tl() for dialog in dialogs],
        "messages": messages,
        "chats": [],
        "users": list(users.values()),
    }


# noinspection PyUnusedLocal
@handler.on_request(GetDialogs, ReqHandlerFlags.AUTH_REQUIRED)
async def get_dialogs(client: Client, request: GetDialogs, user: User):
    return Dialogs(**(
        await get_dialogs_internal(None, user, request.offset_id, request.offset_date, request.limit)
    ))


# noinspection PyUnusedLocal
@handler.on_request(GetPeerDialogs, ReqHandlerFlags.AUTH_REQUIRED)
async def get_peer_dialogs(client: Client, request: GetPeerDialogs, user: User):
    return PeerDialogs(
        **(await get_dialogs_internal(request.peers, user)),
        state=await get_state_internal(user)
    )


# noinspection PyUnusedLocal
@handler.on_request(GetAttachMenuBots)
async def get_attach_menu_bots(client: Client, request: GetAttachMenuBots):
    return AttachMenuBots(
        hash=0,
        bots=[],
        users=[],
    )


# noinspection PyUnusedLocal
@handler.on_request(GetPinnedDialogs, ReqHandlerFlags.AUTH_REQUIRED)
async def get_pinned_dialogs(client: Client, request: GetPinnedDialogs, user: User):
    return PeerDialogs(
        dialogs=[],
        messages=[],
        chats=[],
        users=[],
        state=await get_state_internal(user),
    )


# noinspection PyUnusedLocal
@handler.on_request(ReorderPinnedDialogs)
async def reorder_pinned_dialogs(client: Client, request: ReorderPinnedDialogs):
    return True


# noinspection PyUnusedLocal
@handler.on_request(GetStickers)
async def get_stickers(client: Client, request: GetStickers):
    return Stickers(hash=0, stickers=[])


# noinspection PyUnusedLocal
@handler.on_request(GetDefaultHistoryTTL)
async def get_default_history_ttl(client: Client, request: GetDefaultHistoryTTL):
    return DefaultHistoryTTL(period=10)


# noinspection PyUnusedLocal
@handler.on_request(GetSearchResultsPositions)
async def get_search_results_positions(client: Client, request: GetSearchResultsPositions):
    return SearchResultsPositions(
        count=0,
        positions=[],
    )


# noinspection PyUnusedLocal
@handler.on_request(Search, ReqHandlerFlags.AUTH_REQUIRED)
async def messages_search(client: Client, request: Search, user: User):
    if (chat := await Chat.from_input_peer(user, request.peer)) is None:
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    query = Q(chat=chat)
    query &= Q(message__istartswith=request.q)
    if isinstance(request.from_id, (InputPeerUser, InputPeerSelf)):
        if isinstance(request.from_id, InputPeerUser):
            query &= Q(author__id=request.from_id.user_id)
        else:
            query &= Q(author__id=user.id)

    limit = max(min(100, request.limit), 1)
    messages = await Message.filter(query).limit(limit)

    return Messages(
        messages=[],
        chats=[],
        users=[],
    )


# noinspection PyUnusedLocal
@handler.on_request(GetSearchCounters)
async def get_search_counters(client: Client, request: GetSearchCounters):
    return [
        SearchCounter(filter=flt, count=0) for flt in request.filters
    ]


# noinspection PyUnusedLocal
@handler.on_request(GetSuggestedDialogFilters)
async def get_suggested_dialog_filters(client: Client, request: GetSuggestedDialogFilters):
    return []


# noinspection PyUnusedLocal
@handler.on_request(GetFeaturedStickers)
@handler.on_request(GetFeaturedEmojiStickers)
async def get_featured_stickers(client: Client, request: GetFeaturedStickers | GetFeaturedEmojiStickers):
    return FeaturedStickers(
        hash=0,
        count=0,
        sets=[],
        unread=[],
    )


# noinspection PyUnusedLocal
@handler.on_request(GetAllDrafts, ReqHandlerFlags.AUTH_REQUIRED)
async def get_all_drafts(client: Client, request: GetAllDrafts, user: User):
    users = {}
    updates = []
    drafts = await MessageDraft.filter(dialog__user=user).select_related("dialog", "dialog__chat")
    for draft in drafts:
        updates.append(UpdateDraftMessage(
            peer=await draft.dialog.chat.get_peer(user),
            draft=await draft.to_tl(),
        ))
        users_, _ = await draft.dialog.chat.to_tl_users_chats(user, users)
        users.update(users_)

    return Updates(
        updates=updates,
        users=list(users.values()),
        chats=[],
        date=int(time()),
        seq=0,
    )


# noinspection PyUnusedLocal
@handler.on_request(GetFavedStickers)
async def get_faved_stickers(client: Client, request: GetFavedStickers):
    return FavedStickers(
        hash=0,
        packs=[],
        stickers=[],
    )


# noinspection PyUnusedLocal
@handler.on_request(SearchGlobal, ReqHandlerFlags.AUTH_REQUIRED)
async def search_global(client: Client, request: SearchGlobal, user: User):
    messages = []
    users = []

    q = user_q = request.q
    if q.startswith("@"):
        user_q = q[1:]
    if username_regex_no_len.match(user_q):
        users = await User.filter(username__istartswith=user_q).limit(10)

    messages = await Message.filter(
        chat__id__in=Subquery(Dialog.filter(user=user).values_list("chat_id", flat=True)),
        message__istartswith=q,
    ).select_related("chat", "author").order_by("-date").limit(10)

    return Messages(
        messages=[await message.to_tl(user) for message in messages],
        chats=[],
        users=[await oth_user.to_tl(user) for oth_user in users],
    )


# noinspection PyUnusedLocal
@handler.on_request(GetCustomEmojiDocuments)
async def get_custom_emoji_documents(client: Client, request: GetCustomEmojiDocuments):
    return [DocumentEmpty(id=doc) for doc in request.document_id]


# noinspection PyUnusedLocal
@handler.on_request(GetMessagesReactions)
async def get_messages_reactions(client: Client, request: GetMessagesReactions):
    return Updates(updates=[], users=[], chats=[], date=int(time()), seq=0)


# noinspection PyUnusedLocal
@handler.on_request(GetArchivedStickers)
async def get_archived_stickers(client: Client, request: GetArchivedStickers):
    return ArchivedStickers(count=0, sets=[])


# noinspection PyUnusedLocal
@handler.on_request(GetEmojiStickers)
async def get_emoji_stickers(client: Client, request: GetEmojiStickers):
    return AllStickers(hash=request.hash, sets=[])


# noinspection PyUnusedLocal
@handler.on_request(GetEmojiKeywords)
async def get_emoji_keywords(client: Client, request: GetEmojiKeywords):
    return EmojiKeywordsDifference(lang_code=request.lang_code, from_version=0, version=0, keywords=[])


# noinspection PyUnusedLocal
@handler.on_request(DeleteMessages, ReqHandlerFlags.AUTH_REQUIRED)
async def delete_messages(client: Client, request: DeleteMessages, user: User):
    # TODO: request.revoke

    ids = request.id[:100]
    delete_ids = defaultdict(list)
    chats = {}
    for message in await Message.filter(id__in=ids, chat__dialogs__user=user).select_related("chat"):
        if message.chat.id not in chats:
            chats[message.chat.id] = message.chat
        delete_ids[message.chat.id].append(message.id)

    all_ids = [i for ids in delete_ids.values() for i in ids]
    await Message.filter(id__in=all_ids).delete()

    if not all_ids:
        updates_state, _ = await State.get_or_create(user=user)
        return AffectedMessages(pts=updates_state.pts, pts_count=0)

    pts = await UpdatesManager().delete_messages(user, list(chats.values()), delete_ids)
    return AffectedMessages(pts=pts, pts_count=len(all_ids))


# noinspection PyUnusedLocal
@handler.on_request(GetWebPagePreview)
async def get_webpage_preview(client: Client, request: GetWebPagePreview):
    return WebPageEmpty(id=0)


# noinspection PyUnusedLocal
@handler.on_request(EditMessage, ReqHandlerFlags.AUTH_REQUIRED)
async def edit_message(client: Client, request: EditMessage, user: User):
    if (chat := await Chat.from_input_peer(user, request.peer)) is None:
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    if (message := await Message.get_or_none(chat=chat, id=request.id).select_related("chat", "author")) is None:
        raise ErrorRpc(error_code=400, error_message="MESSAGE_ID_INVALID")

    if not request.message:
        raise ErrorRpc(error_code=400, error_message="MESSAGE_EMPTY")
    if message.author != user:
        raise ErrorRpc(error_code=403, error_message="MESSAGE_AUTHOR_REQUIRED")
    if message.message == request.message:
        raise ErrorRpc(error_code=400, error_message="MESSAGE_NOT_MODIFIED")

    await message.update(message=request.message, edit_date=datetime.now())
    return await UpdatesManager.edit_message(message)


# noinspection PyUnusedLocal
@handler.on_request(SendMedia, ReqHandlerFlags.AUTH_REQUIRED)
async def send_media(client: Client, request: SendMedia, user: User):
    if (chat := await Chat.from_input_peer(user, request.peer, True)) is None:
        raise ErrorRpc(error_code=500, error_message="Failed to create chat")

    if not isinstance(request.media, (InputMediaUploadedDocument, InputMediaUploadedPhoto)):
        raise ErrorRpc(error_code=400, error_message="MEDIA_INVALID")
    if len(request.message) > 2000:
        raise ErrorRpc(error_code=400, error_message="MEDIA_CAPTION_TOO_LONG")

    mime = request.media.mime_type if isinstance(request.media, InputMediaUploadedDocument) else "image/jpeg"
    attributes = request.media.attributes if isinstance(request.media, InputMediaUploadedDocument) else []
    media_type = MediaType.DOCUMENT if isinstance(request.media, InputMediaUploadedDocument) else MediaType.PHOTO

    file = await upload_file(user, request.media.file, mime, attributes)
    sizes = await resize_photo(str(file.physical_id))
    stripped = await generate_stripped(str(file.physical_id))
    await file.update(attributes=file.attributes | {"_sizes": sizes, "_size_stripped": stripped.hex()})

    reply = None
    if request.reply_to is not None:
        reply = await Message.get_or_none(id=request.reply_to.reply_to_msg_id, chat=chat)

    message = await Message.create(message=request.message, author=user, chat=chat, reply_to=reply)
    await MessageMedia.create(file=file, message=message, spoiler=request.media.spoiler, type=media_type)
    await MessageDraft.filter(dialog__chat=chat, dialog__user=user).delete()
    await send_update_draft(user, chat, DraftMessageEmpty())

    if (upd := await UpdatesManager().send_message(user, message, True)) is None:
        assert False, "unknown chat type ?"

    return upd


# noinspection PyUnusedLocal
@handler.on_request(GetMessageEditData, ReqHandlerFlags.AUTH_REQUIRED)
async def get_message_edit_data(client: Client, request: GetMessageEditData, user: User):
    return MessageEditData()


async def send_update_draft(user: User, chat: Chat, draft: MessageDraft | DraftMessage | DraftMessageEmpty):
    if isinstance(draft, MessageDraft):
        draft = await draft.to_tl()

    updates = Updates(
        updates=[UpdateDraftMessage(peer=await chat.get_peer(user), draft=draft)],
        users=[await user.to_tl(user)],
        chats=[],
        date=int(time()),
        seq=0,
    )

    await SessionManager().send(updates, user.id)


# noinspection PyUnusedLocal
@handler.on_request(SaveDraft, ReqHandlerFlags.AUTH_REQUIRED)
async def save_draft(client: Client, request: SaveDraft, user: User):
    if (chat := await Chat.from_input_peer(user, request.peer, True)) is None:
        raise ErrorRpc(error_code=500, error_message="Failed to create chat")

    dialog = await Dialog.get(user=user, chat=chat)
    draft, _ = await MessageDraft.get_or_create(
        dialog=dialog,
        defaults={"message": request.message, "date": datetime.now()}
    )

    await send_update_draft(user, chat, draft)
    return True
