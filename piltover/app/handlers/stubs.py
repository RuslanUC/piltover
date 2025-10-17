from piltover.enums import ReqHandlerFlags
from piltover.tl import WebPageEmpty, AttachMenuBots, DefaultHistoryTTL, EmojiKeywordsDifference, \
    DocumentEmpty, PeerSettings, TLObjectVector
from piltover.tl.functions.channels import GetSponsoredMessages_133
from piltover.tl.functions.messages import GetPeerSettings, GetScheduledHistory, GetQuickReplies, GetMessageEditData, \
    GetEmojiKeywordsLanguages, GetWebPage, GetTopReactions, GetAttachMenuBots, \
    GetStickers, GetSearchResultsPositions, GetDefaultHistoryTTL, GetSuggestedDialogFilters, GetSavedReactionTags, \
    GetFeaturedStickers, GetFeaturedEmojiStickers, GetFavedStickers, GetCustomEmojiDocuments, GetArchivedStickers, \
    GetEmojiStickers, GetEmojiKeywords, GetWebPagePreview, GetDefaultTagReactions, \
    GetEmojiKeywordsDifference, GetSponsoredMessages, GetSavedGifs
from piltover.tl.functions.premium import GetBoostsStatus
from piltover.tl.types.messages import PeerSettings as MessagesPeerSettings, Messages, Reactions, SavedReactionTags, \
    Stickers, SearchResultsPositions, AllStickers, FavedStickers, ArchivedStickers, FeaturedStickers, MessageEditData, \
    QuickReplies, SponsoredMessages, SponsoredMessagesEmpty, SavedGifs, SavedGifsNotModified
from piltover.tl.types.premium import BoostsStatus
from piltover.worker import MessageHandler

handler = MessageHandler("stubs")


@handler.on_request(GetBoostsStatus, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_boosts_status() -> BoostsStatus:  # pragma: no cover
    return BoostsStatus(
        my_boost=True,
        level=3,
        current_level_boosts=100,
        boosts=100,
        boost_url="http://127.0.0.1"
    )


@handler.on_request(GetSponsoredMessages_133, ReqHandlerFlags.AUTH_NOT_REQUIRED)
@handler.on_request(GetSponsoredMessages, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_sponsored_messages() -> SponsoredMessages | SponsoredMessagesEmpty:  # pragma: no cover
    return SponsoredMessagesEmpty()


@handler.on_request(GetSavedGifs)
async def get_saved_gifs() -> SavedGifs | SavedGifsNotModified:
    return SavedGifsNotModified()
