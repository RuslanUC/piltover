from piltover.enums import ReqHandlerFlags
from piltover.tl import WebPageEmpty, AttachMenuBots, EmojiKeywordsDifference, \
    PeerSettings, TLObjectVector
from piltover.tl.base.channels import SponsoredMessageReportResult
from piltover.tl.functions.channels import GetSponsoredMessages_133
from piltover.tl.functions.messages import GetPeerSettings, GetQuickReplies, GetMessageEditData, \
    GetEmojiKeywordsLanguages, GetWebPage, GetTopReactions, GetAttachMenuBots, \
    GetStickers, GetSuggestedDialogFilters, GetSavedReactionTags, \
    GetFeaturedStickers, GetFeaturedEmojiStickers, GetEmojiKeywords, GetWebPagePreview, GetDefaultTagReactions, \
    GetEmojiKeywordsDifference, GetAvailableEffects, GetSponsoredMessages, ReportSponsoredMessage, ViewSponsoredMessage, \
    ClickSponsoredMessage
from piltover.tl.types.channels import SponsoredMessageReportResultReported
from piltover.tl.types.messages import PeerSettings as MessagesPeerSettings, Reactions, SavedReactionTags, \
    Stickers, FeaturedStickers, MessageEditData, \
    QuickReplies, AvailableEffects, SponsoredMessages, SponsoredMessagesEmpty
from piltover.worker import MessageHandler

handler = MessageHandler("messages.stubs")


@handler.on_request(GetPeerSettings, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_peer_settings():  # pragma: no cover
    return MessagesPeerSettings(
        settings=PeerSettings(),
        chats=[],
        users=[],
    )


@handler.on_request(GetEmojiKeywordsLanguages, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_emoji_keywords_languages():  # pragma: no cover
    return TLObjectVector()


@handler.on_request(GetWebPage, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_web_page():  # pragma: no cover
    return WebPageEmpty(id=0)


@handler.on_request(GetTopReactions, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_top_reactions():  # pragma: no cover
    return Reactions(hash=0, reactions=[])


@handler.on_request(GetAttachMenuBots, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_attach_menu_bots():  # pragma: no cover
    return AttachMenuBots(
        hash=0,
        bots=[],
        users=[],
    )


@handler.on_request(GetStickers, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_stickers():  # pragma: no cover
    return Stickers(hash=0, stickers=[])


@handler.on_request(GetSuggestedDialogFilters, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_suggested_dialog_filters():  # pragma: no cover
    return TLObjectVector()


@handler.on_request(GetFeaturedStickers, ReqHandlerFlags.AUTH_NOT_REQUIRED)
@handler.on_request(GetFeaturedEmojiStickers, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_featured_stickers():  # pragma: no cover
    return FeaturedStickers(
        hash=0,
        count=0,
        sets=[],
        unread=[],
    )


@handler.on_request(GetEmojiKeywords, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_emoji_keywords(request: GetEmojiKeywords):  # pragma: no cover
    return EmojiKeywordsDifference(lang_code=request.lang_code, from_version=0, version=0, keywords=[])


@handler.on_request(GetWebPagePreview, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_webpage_preview():  # pragma: no cover
    return WebPageEmpty(id=0)


@handler.on_request(GetMessageEditData, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_message_edit_data():  # pragma: no cover
    return MessageEditData(caption=True)


@handler.on_request(GetQuickReplies, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_quick_replies() -> QuickReplies:  # pragma: no cover
    return QuickReplies(
        quick_replies=[],
        messages=[],
        chats=[],
        users=[],
    )


@handler.on_request(GetDefaultTagReactions, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_default_tag_reactions() -> Reactions:  # pragma: no cover
    return Reactions(
        hash=0,
        reactions=[],
    )


@handler.on_request(GetSavedReactionTags, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_saved_reaction_tags() -> SavedReactionTags:  # pragma: no cover
    return SavedReactionTags(
        tags=[],
        hash=0,
    )


@handler.on_request(GetEmojiKeywordsDifference, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_emoji_keywords_difference(
        request: GetEmojiKeywordsDifference,
) -> EmojiKeywordsDifference:  # pragma: no cover
    return EmojiKeywordsDifference(
        lang_code=request.lang_code,
        from_version=request.from_version,
        version=request.from_version,
        keywords=[],
    )


@handler.on_request(GetAvailableEffects, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_available_effects() -> AvailableEffects:  # pragma: no cover
    return AvailableEffects(
        hash=0,
        effects=[],
        documents=[],
    )


@handler.on_request(GetSponsoredMessages_133, ReqHandlerFlags.AUTH_NOT_REQUIRED)
@handler.on_request(GetSponsoredMessages, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_sponsored_messages() -> SponsoredMessages | SponsoredMessagesEmpty:  # pragma: no cover
    return SponsoredMessagesEmpty()

    # return SponsoredMessages(
    #     messages=[
    #         SponsoredMessage(
    #             recommended=True,
    #             can_report=True,
    #             random_id=urandom(16),
    #             url="t.me",
    #             title=f"{i}",
    #             message=f"{i}",
    #             entities=None,
    #             photo=None,
    #             media=None,
    #             color=None,
    #             button_text=f"{i}",
    #             sponsor_info=None,
    #             additional_info=None,
    #         ) for i in range(10000)
    #     ],
    #     chats=[],
    #     users=[],
    # )


@handler.on_request(ReportSponsoredMessage, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def report_sponsored_message() -> SponsoredMessageReportResult:  # pragma: no cover
    return SponsoredMessageReportResultReported()


@handler.on_request(ClickSponsoredMessage, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def click_sponsored_message() -> bool:  # pragma: no cover
    return True


@handler.on_request(ViewSponsoredMessage, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def view_sponsored_message() -> bool:  # pragma: no cover
    return True
