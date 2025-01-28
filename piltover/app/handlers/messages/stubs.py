from time import time

from piltover.enums import ReqHandlerFlags
from piltover.exceptions import ErrorRpc
from piltover.tl import WebPageEmpty, AttachMenuBots, DefaultHistoryTTL, Updates, EmojiKeywordsDifference, \
    DocumentEmpty, PeerSettings, InputStickerSetAnimatedEmoji, StickerSet
from piltover.tl.functions.messages import GetDialogFilters, GetPeerSettings, GetScheduledHistory, \
    GetEmojiKeywordsLanguages, GetWebPage, GetStickerSet, GetRecentReactions, GetTopReactions, GetSavedHistory, \
    GetAttachMenuBots, GetStickers, GetSearchResultsPositions, GetDefaultHistoryTTL, GetSuggestedDialogFilters, \
    GetFeaturedStickers, GetFeaturedEmojiStickers, GetFavedStickers, GetCustomEmojiDocuments, GetMessagesReactions, \
    GetArchivedStickers, GetEmojiStickers, GetEmojiKeywords, GetWebPagePreview, GetMessageEditData, GetQuickReplies, \
    GetDefaultTagReactions, GetSavedDialogs, GetSavedReactionTags, GetEmojiKeywordsDifference
from piltover.tl.types.messages import PeerSettings as MessagesPeerSettings, Messages, Reactions, SavedReactionTags, \
    Stickers, SearchResultsPositions, AllStickers, FavedStickers, ArchivedStickers, FeaturedStickers, MessageEditData, \
    StickerSet as messages_StickerSet, QuickReplies, SavedDialogs
from piltover.worker import MessageHandler

handler = MessageHandler("messages.stubs")

@handler.on_request(GetDialogFilters, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_dialog_filters():
    return []


@handler.on_request(GetPeerSettings, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_peer_settings():
    return MessagesPeerSettings(
        settings=PeerSettings(),
        chats=[],
        users=[],
    )


@handler.on_request(GetScheduledHistory, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_scheduled_history():
    return Messages(messages=[], chats=[], users=[])


@handler.on_request(GetEmojiKeywordsLanguages, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_emoji_keywords_languages():
    return []


@handler.on_request(GetWebPage, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_web_page():
    return WebPageEmpty(id=0)


@handler.on_request(GetStickerSet, ReqHandlerFlags.AUTH_NOT_REQUIRED)
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


@handler.on_request(GetTopReactions, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_top_reactions():
    return Reactions(hash=0, reactions=[])


@handler.on_request(GetRecentReactions, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_recent_reactions():
    return Reactions(hash=0, reactions=[])


@handler.on_request(GetAttachMenuBots, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_attach_menu_bots():
    return AttachMenuBots(
        hash=0,
        bots=[],
        users=[],
    )


@handler.on_request(GetStickers, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_stickers():
    return Stickers(hash=0, stickers=[])


@handler.on_request(GetDefaultHistoryTTL, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_default_history_ttl():
    return DefaultHistoryTTL(period=10)


@handler.on_request(GetSearchResultsPositions, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_search_results_positions():
    return SearchResultsPositions(
        count=0,
        positions=[],
    )


@handler.on_request(GetSuggestedDialogFilters, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_suggested_dialog_filters():
    return []


@handler.on_request(GetFeaturedStickers, ReqHandlerFlags.AUTH_NOT_REQUIRED)
@handler.on_request(GetFeaturedEmojiStickers, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_featured_stickers():
    return FeaturedStickers(
        hash=0,
        count=0,
        sets=[],
        unread=[],
    )


@handler.on_request(GetFavedStickers, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_faved_stickers():
    return FavedStickers(
        hash=0,
        packs=[],
        stickers=[],
    )


@handler.on_request(GetCustomEmojiDocuments, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_custom_emoji_documents(request: GetCustomEmojiDocuments):
    return [DocumentEmpty(id=doc) for doc in request.document_id]


@handler.on_request(GetMessagesReactions, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_messages_reactions():
    return Updates(updates=[], users=[], chats=[], date=int(time()), seq=0)


@handler.on_request(GetArchivedStickers, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_archived_stickers():
    return ArchivedStickers(count=0, sets=[])


@handler.on_request(GetEmojiStickers, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_emoji_stickers(request: GetEmojiStickers):
    return AllStickers(hash=request.hash, sets=[])


@handler.on_request(GetEmojiKeywords, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_emoji_keywords(request: GetEmojiKeywords):
    return EmojiKeywordsDifference(lang_code=request.lang_code, from_version=0, version=0, keywords=[])


@handler.on_request(GetWebPagePreview, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_webpage_preview():
    return WebPageEmpty(id=0)


@handler.on_request(GetMessageEditData, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_message_edit_data():
    return MessageEditData()


@handler.on_request(GetQuickReplies, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_quick_replies() -> QuickReplies:
    return QuickReplies(
        quick_replies=[],
        messages=[],
        chats=[],
        users=[],
    )


@handler.on_request(GetDefaultTagReactions, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_default_tag_reactions() -> Reactions:
    return Reactions(
        hash=0,
        reactions=[],
    )


@handler.on_request(GetSavedDialogs, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_saved_dialogs() -> SavedDialogs:
    return SavedDialogs(
        dialogs=[],
        messages=[],
        chats=[],
        users=[],
    )


@handler.on_request(GetSavedReactionTags, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_saved_reaction_tags() -> SavedReactionTags:
    return SavedReactionTags(
        tags=[],
        hash=0,
    )


@handler.on_request(GetSavedHistory, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_saved_history() -> Messages:
    return Messages(
        messages=[],
        chats=[],
        users=[],
    )


@handler.on_request(GetEmojiKeywordsDifference, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_emoji_keywords_difference(request: GetEmojiKeywordsDifference) -> EmojiKeywordsDifference:
    return EmojiKeywordsDifference(
        lang_code=request.lang_code,
        from_version=request.from_version,
        version=request.from_version,
        keywords=[],
    )
