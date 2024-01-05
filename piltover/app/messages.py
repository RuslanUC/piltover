from time import time

from piltover.app.updates import get_state
from piltover.app.utils import auth_required
from piltover.db.enums import ChatType
from piltover.db.models import User, Chat, Dialog
from piltover.db.models.message import Message
from piltover.exceptions import ErrorRpc
from piltover.server import MessageHandler, Client
from piltover.tl.types import CoreMessage
from piltover.tl_new import WebPageEmpty, StickerSet, \
    AttachMenuBots, \
    DefaultHistoryTTL, Updates, InputPeerUser, UpdateMessageID, UpdateNewMessage, UpdateReadHistoryInbox, InputPeerSelf, \
    EmojiKeywordsDifference
from piltover.tl_new.functions.messages import GetDialogFilters, GetAvailableReactions, SetTyping, GetPeerSettings, \
    GetScheduledHistory, GetEmojiKeywordsLanguages, GetPeerDialogs, GetHistory, GetWebPage, SendMessage, ReadHistory, \
    GetStickerSet, GetRecentReactions, GetTopReactions, GetDialogs, GetAttachMenuBots, GetPinnedDialogs, \
    ReorderPinnedDialogs, GetStickers, GetSearchCounters, Search, GetSearchResultsPositions, GetDefaultHistoryTTL, \
    GetSuggestedDialogFilters, GetFeaturedStickers, GetFeaturedEmojiStickers, GetAllDrafts, SearchGlobal, \
    GetFavedStickers, GetCustomEmojiDocuments, GetMessagesReactions, GetArchivedStickers, GetEmojiStickers, \
    GetEmojiKeywords, DeleteMessages
from piltover.tl_new.types.messages import AvailableReactions, PeerSettings, Messages, PeerDialogs, AffectedMessages, \
    StickerSet as MsgStickerSet, Reactions, Dialogs, Stickers, SearchResultsPositions, SearchCounter, FeaturedStickers, \
    FavedStickers, ArchivedStickers, AllStickers

handler = MessageHandler("messages")


# noinspection PyUnusedLocal
@handler.on_message(GetDialogFilters)
async def get_dialog_filters(client: Client, request: CoreMessage[GetDialogFilters], session_id: int):
    return []


# noinspection PyUnusedLocal
@handler.on_message(GetAvailableReactions)
async def get_available_reactions(client: Client, request: CoreMessage[GetAvailableReactions], session_id: int):
    return AvailableReactions(hash=0, reactions=[])


# noinspection PyUnusedLocal
@handler.on_message(SetTyping)
async def set_typing(client: Client, request: CoreMessage[SetTyping], session_id: int):
    return True


# noinspection PyUnusedLocal
@handler.on_message(GetPeerSettings)
async def get_peer_settings(client: Client, request: CoreMessage[GetPeerSettings], session_id: int):
    return PeerSettings()


# noinspection PyUnusedLocal
@handler.on_message(GetScheduledHistory)
async def get_scheduled_history(client: Client, request: CoreMessage[GetScheduledHistory], session_id: int):
    return Messages(messages=[], chats=[], users=[])


# noinspection PyUnusedLocal
@handler.on_message(GetEmojiKeywordsLanguages)
async def get_emoji_keywords_languages(client: Client, request: CoreMessage[GetEmojiKeywordsLanguages],
                                       session_id: int):
    return []


# noinspection PyUnusedLocal
@handler.on_message(GetHistory)
@auth_required
async def get_history(client: Client, request: CoreMessage[GetHistory], session_id: int, user: User):
    if isinstance(request.obj.peer, InputPeerSelf):
        chat = await Chat.get_private(user)
    elif isinstance(request.obj.peer, InputPeerUser):
        if (to_user := await User.get_or_none(id=request.obj.peer.user_id)) is None:
            raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")
        chat = await Chat.get_private(user, to_user)
    else:
        raise ErrorRpc(error_code=400, error_message="PEER_ID_NOT_SUPPORTED")

    if chat is None:
        return Messages(messages=[], chats=[], users=[])

    limit = request.obj.limit
    if limit > 100 or limit < 1:
        limit = 100
    query = {}
    if request.obj.max_id > 0:
        query["id__lte"] = request.obj.max_id
    if request.obj.min_id > 0:
        query["id__gte"] = request.obj.min_id

    messages = await Message.filter(chat=chat, **query).select_related("author", "chat").limit(limit).all()
    if not messages:
        return Messages(messages=[], chats=[], users=[])

    users = {}
    for message in messages:
        if message.author.id in users:
            continue
        users[message.author.id] = message.author.to_tl(user)

    return Messages(
        messages=[await message.to_tl(user) for message in messages],
        chats=[],
        users=list(users.values()),
    )


# noinspection PyUnusedLocal
@handler.on_message(SendMessage)
@auth_required
async def send_message(client: Client, request: CoreMessage[SendMessage], session_id: int, user: User):
    if isinstance(request.obj.peer, InputPeerUser) and request.obj.peer.user_id == user.id:
        request.obj.peer = InputPeerSelf()

    if isinstance(request.obj.peer, InputPeerSelf):
        chat = await Chat.get_or_create_private(user)
    elif isinstance(request.obj.peer, InputPeerUser):
        if (to_user := await User.get_or_none(id=request.obj.peer.user_id)) is None:
            raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")
        chat = await Chat.get_or_create_private(user, to_user)
    else:
        raise ErrorRpc(error_code=400, error_message="PEER_ID_NOT_SUPPORTED")

    message = await Message.create(message=request.obj.message, author=user, chat=chat)

    return Updates(
        updates=[
            UpdateMessageID(id=message.id, random_id=request.obj.random_id),
            UpdateNewMessage(message=await message.to_tl(user), pts=1, pts_count=1),
            UpdateReadHistoryInbox(peer=await chat.get_peer(user), max_id=message.id, still_unread_count=0, pts=2,
                                   pts_count=1)
        ],
        users=[user.to_tl(user)],
        chats=[],
        date=int(time()),
        seq=1,
    )


# noinspection PyUnusedLocal
@handler.on_message(ReadHistory)
async def read_history(client: Client, request: CoreMessage[ReadHistory], session_id: int):
    return AffectedMessages(
        pts=3,
        pts_count=1,
    )


# noinspection PyUnusedLocal
@handler.on_message(GetWebPage)
async def get_web_page(client: Client, request: CoreMessage[GetWebPage], session_id: int):
    return WebPageEmpty(id=0)


# noinspection PyUnusedLocal
@handler.on_message(GetStickerSet)
async def get_sticker_set(client: Client, request: CoreMessage[GetStickerSet], session_id: int):
    import random
    return MsgStickerSet(
        set=StickerSet(
            official=True,
            id=random.randint(1000000, 9000000),
            access_hash=random.randint(1000000, 9000000),
            title="Picker Stack",
            short_name=random.randbytes(5).hex(),
            count=0,
            hash=0,
        ),
        packs=[],
        keywords=[],
        documents=[],
    )


# noinspection PyUnusedLocal
@handler.on_message(GetTopReactions)
async def get_top_reactions(client: Client, request: CoreMessage[GetTopReactions], session_id: int):
    return Reactions(hash=0, reactions=[])


# noinspection PyUnusedLocal
@handler.on_message(GetRecentReactions)
async def get_recent_reactions(client: Client, request: CoreMessage[GetRecentReactions], session_id: int):
    return Reactions(hash=0, reactions=[])


async def get_dialogs_internal(peers: list | None, user: User):
    # TODO: get dialogs by peers

    dialogs = await Dialog.filter(user=user).select_related("user", "chat").all()
    messages = []
    users = {}
    for dialog in dialogs:
        if (message := await Message.filter(chat=dialog.chat).select_related("author", "chat").order_by("-id")
                .first()) is not None:
            messages.append(await message.to_tl(user))
        if dialog.chat.type in {ChatType.PRIVATE, ChatType.SAVED}:
            peer = await dialog.chat.get_peer(user)
            if peer.user_id not in users:
                users[peer.user_id] = (await User.get(id=peer.user_id)).to_tl(user)

    return {
        "dialogs": [await dialog.to_tl() for dialog in dialogs],
        "messages": messages,
        "chats": [],
        "users": list(users.values()),
    }


# noinspection PyUnusedLocal
@handler.on_message(GetDialogs)
@auth_required
async def get_dialogs(client: Client, request: CoreMessage[GetDialogs], session_id: int, user: User):
    return Dialogs(**(await get_dialogs_internal(None, user)))


@handler.on_message(GetPeerDialogs)
@auth_required
async def get_peer_dialogs(client: Client, request: CoreMessage[GetPeerDialogs], session_id: int, user: User):
    return PeerDialogs(
        **(await get_dialogs_internal(request.obj.peers, user)),
        state=await get_state(client, request, session_id)
    )


# noinspection PyUnusedLocal
@handler.on_message(GetAttachMenuBots)
async def get_attach_menu_bots(client: Client, request: CoreMessage[GetAttachMenuBots], session_id: int):
    return AttachMenuBots(
        hash=0,
        bots=[],
        users=[],
    )


@handler.on_message(GetPinnedDialogs)
async def get_pinned_dialogs(client: Client, request: CoreMessage[GetPinnedDialogs], session_id: int):
    return PeerDialogs(
        dialogs=[],
        messages=[],
        chats=[],
        users=[],
        state=await get_state(client, request, session_id),
    )


# noinspection PyUnusedLocal
@handler.on_message(ReorderPinnedDialogs)
async def reorder_pinned_dialogs(client: Client, request: CoreMessage[ReorderPinnedDialogs], session_id: int):
    return True


# noinspection PyUnusedLocal
@handler.on_message(GetStickers)
async def get_stickers(client: Client, request: CoreMessage[GetStickers], session_id: int):
    return Stickers(hash=0, stickers=[])


# noinspection PyUnusedLocal
@handler.on_message(GetDefaultHistoryTTL)
async def get_default_history_ttl(client: Client, request: CoreMessage[GetDefaultHistoryTTL], session_id: int):
    return DefaultHistoryTTL(period=10)


# noinspection PyUnusedLocal
@handler.on_message(GetSearchResultsPositions)
async def get_search_results_positions(client: Client, request: CoreMessage[GetSearchResultsPositions],
                                       session_id: int):
    return SearchResultsPositions(
        count=0,
        positions=[],
    )


# noinspection PyUnusedLocal
@handler.on_message(Search)
async def messages_search(client: Client, request: CoreMessage[Search], session_id: int):
    return Messages(
        messages=[],
        chats=[],
        users=[],
    )


# noinspection PyUnusedLocal
@handler.on_message(GetSearchCounters)
async def get_search_counters(client: Client, request: CoreMessage[GetSearchCounters], session_id: int):
    return [
        SearchCounter(filter=flt, count=0) for flt in request.obj.filters
    ]


# noinspection PyUnusedLocal
@handler.on_message(GetSuggestedDialogFilters)
async def get_suggested_dialog_filters(client: Client, request: CoreMessage[GetSuggestedDialogFilters],
                                       session_id: int):
    return []


# noinspection PyUnusedLocal
@handler.on_message(GetFeaturedStickers)
@handler.on_message(GetFeaturedEmojiStickers)
async def get_featured_stickers(client: Client,
                                request: CoreMessage[GetFeaturedStickers | GetFeaturedEmojiStickers],
                                session_id: int):
    return FeaturedStickers(
        hash=0,
        count=0,
        sets=[],
        unread=[],
    )


# noinspection PyUnusedLocal
@handler.on_message(GetAllDrafts)
async def get_all_drafts(client: Client, request: CoreMessage[GetAllDrafts], session_id: int):
    return Updates(
        updates=[],  # list of updateDraftMessage
        users=[],
        chats=[],
        date=int(time()),
        seq=0,
    )


# noinspection PyUnusedLocal
@handler.on_message(GetFavedStickers)
async def get_faved_stickers(client: Client, request: CoreMessage[GetFavedStickers], session_id: int):
    return FavedStickers(
        hash=0,
        packs=[],
        stickers=[],
    )


# noinspection PyUnusedLocal
@handler.on_message(SearchGlobal)
async def search_global(client: Client, request: CoreMessage[SearchGlobal], session_id: int):
    return Messages(
        messages=[],
        chats=[],
        users=[],
    )


# noinspection PyUnusedLocal
@handler.on_message(GetCustomEmojiDocuments)
async def get_custom_emoji_documents(client: Client, request: CoreMessage[GetCustomEmojiDocuments], session_id: int):
    return []


@handler.on_message(GetMessagesReactions)
async def get_messages_reactions(client: Client, request: CoreMessage[GetMessagesReactions], session_id: int):
    return Updates(updates=[], users=[], chats=[], date=int(time()), seq=0)


@handler.on_message(GetArchivedStickers)
async def get_archived_stickers(client: Client, request: CoreMessage[GetArchivedStickers], session_id: int):
    return ArchivedStickers(count=0, sets=[])


@handler.on_message(GetEmojiStickers)
async def get_emoji_stickers(client: Client, request: CoreMessage[GetEmojiStickers], session_id: int):
    return AllStickers(hash=request.obj.hash, sets=[])


@handler.on_message(GetEmojiKeywords)
async def get_emoji_keywords(client: Client, request: CoreMessage[GetEmojiKeywords], session_id: int):
    return EmojiKeywordsDifference(lang_code=request.obj.lang_code, from_version=0, version=0, keywords=[])


@handler.on_message(DeleteMessages)
async def delete_messages(client: Client, request: CoreMessage[DeleteMessages], session_id: int):
    return AffectedMessages(pts=0, pts_count=0)
