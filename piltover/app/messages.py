from time import time

from piltover.app import durov, durov_message, user
from piltover.server import MessageHandler, Client
from piltover.tl.types import CoreMessage
from piltover.tl_new import Dialog, PeerUser, Message, WebPageEmpty, UpdateShortSentMessage, StickerSet, AttachMenuBots, \
    DefaultHistoryTTL, Updates
from piltover.tl_new.functions.messages import GetDialogFilters, GetAvailableReactions, SetTyping, GetPeerSettings, \
    GetScheduledHistory, GetEmojiKeywordsLanguages, GetPeerDialogs, GetHistory, GetWebPage, SendMessage, ReadHistory, \
    GetStickerSet, GetRecentReactions, GetTopReactions, GetDialogs, GetAttachMenuBots, GetPinnedDialogs, \
    ReorderPinnedDialogs, GetStickers, GetSearchCounters, Search, GetSearchResultsPositions, GetDefaultHistoryTTL, \
    GetSuggestedDialogFilters, GetFeaturedStickers, GetFeaturedEmojiStickers, GetAllDrafts, SearchGlobal, \
    GetFavedStickers
from piltover.tl_new.types.messages import AvailableReactions, PeerSettings, Messages, PeerDialogs, AffectedMessages, \
    StickerSet as MsgStickerSet, Reactions, Dialogs, Stickers, SearchResultsPositions, SearchCounter, FeaturedStickers, \
    FavedStickers

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


@handler.on_message(GetPeerDialogs)
async def get_peer_dialogs(client: Client, request: CoreMessage[GetPeerDialogs], session_id: int):
    return PeerDialogs(
        dialogs=[
            Dialog(
                peer=PeerUser(user_id=durov.id),
                top_message=0,
                read_inbox_max_id=0,
                read_outbox_max_id=0,
                unread_count=0,
                unread_mentions_count=0,
                unread_reactions_count=0,
                notify_settings=await get_notify_settings(
                    client, request, session_id
                ),
            )
        ],
        messages=[durov_message],
        chats=[],
        users=[durov],
        state=await get_state(client, request, session_id)
    )


# noinspection PyUnusedLocal
@handler.on_message(GetHistory)
async def get_history(client: Client, request: CoreMessage[GetHistory], session_id: int):
    if request.obj.peer.user_id == durov.id:
        return Messages(messages=[durov_message], chats=[], users=[])
    if request.obj.offset_id != 0:
        return Messages(messages=[], chats=[], users=[])
    return Messages(
        messages=[
            Message(
                out=True,
                mentioned=True,
                media_unread=False,
                silent=False,
                post=True,
                from_scheduled=False,
                legacy=True,
                edit_hide=True,
                pinned=False,
                noforwards=False,
                id=1,
                from_id=PeerUser(user_id=user.id),
                peer_id=PeerUser(user_id=user.id),
                date=int(time() - 120),
                message="aaaaaa",
                media=None,
                entities=None,
                views=40,
                forwards=None,
                edit_date=None,
                post_author=None,
                grouped_id=None,
                reactions=None,
                restriction_reason=None,
                ttl_period=None,
            )
        ],
        chats=[],
        users=[]
    )


# noinspection PyUnusedLocal
@handler.on_message(SendMessage)
async def send_message(client: Client, request: CoreMessage[SendMessage], session_id: int):
    return UpdateShortSentMessage(
        out=True,
        id=2,
        pts=2,
        pts_count=2,
        date=int(time()),
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
    return WebPageEmpty()


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


# noinspection PyUnusedLocal
@handler.on_message(GetDialogs)
async def get_dialogs(client: Client, request: CoreMessage[GetDialogs], session_id: int):
    return Dialogs(
        dialogs=[],
        messages=[],
        chats=[],
        users=[],
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
