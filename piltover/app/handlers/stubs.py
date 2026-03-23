from piltover.enums import ReqHandlerFlags
from piltover.tl import StarsAmount, TLObjectVector, StarsTopupOption, EmojiList
from piltover.tl.functions.account import GetCollectibleEmojiStatuses, GetContactSignUpNotification, \
    SetContactSignUpNotification, GetChannelRestrictedStatusEmojis
from piltover.tl.functions.bots import GetPopularAppBots
from piltover.tl.functions.payments import GetStarsStatus, GetStarsSubscriptions, GetStarsTransactions, \
    GetStarsTopupOptions
from piltover.tl.functions.premium import GetBoostsStatus, GetMyBoosts, GetBoostsList
from piltover.tl.types.account import EmojiStatuses
from piltover.tl.types.bots import PopularAppBots
from piltover.tl.types.payments import StarsStatus
from piltover.tl.types.premium import BoostsStatus, MyBoosts, BoostsList
from piltover.worker import MessageHandler

handler = MessageHandler("stubs")

MAX_I32 = 2 ** 31 - 1
MAX_I64 = 2 ** 63 - 1


NOBOT_NOAUTH = ReqHandlerFlags.BOT_NOT_ALLOWED | ReqHandlerFlags.AUTH_NOT_REQUIRED


@handler.on_request(GetBoostsStatus, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_boosts_status() -> BoostsStatus:  # pragma: no cover
    return BoostsStatus(
        level=MAX_I32,
        current_level_boosts=MAX_I32,
        boosts=MAX_I32,
        boost_url="http://unreachable.local/"
    )


@handler.on_request(GetMyBoosts, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_my_boosts() -> MyBoosts:  # pragma: no cover
    return MyBoosts(my_boosts=[], chats=[], users=[])


@handler.on_request(GetStarsStatus, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_stars_status() -> StarsStatus:  # pragma: no cover
    return StarsStatus(
        balance=StarsAmount(amount=MAX_I64, nanos=0),
        chats=[],
        users=[],
    )


@handler.on_request(GetCollectibleEmojiStatuses, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_collectible_emoji_statuses() -> EmojiStatuses:  # pragma: no cover
    return EmojiStatuses(
        hash=0,
        statuses=[],
    )


@handler.on_request(GetBoostsList, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_boosts_list() -> BoostsList:  # pragma: no cover
    return BoostsList(
        count=MAX_I32,
        boosts=[],
        users=[],
    )


@handler.on_request(GetStarsSubscriptions, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_starts_subscriptions() -> StarsStatus:  # pragma: no cover
    return StarsStatus(
        balance=StarsAmount(amount=MAX_I64, nanos=0),
        chats=[],
        users=[],
    )


@handler.on_request(GetStarsTransactions, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_starts_transactions() -> StarsStatus:  # pragma: no cover
    return StarsStatus(
        balance=StarsAmount(amount=MAX_I64, nanos=0),
        chats=[],
        users=[],
    )


@handler.on_request(GetStarsTopupOptions, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_stars_topup_options() -> list[StarsTopupOption]:  # pragma: no cover
    return TLObjectVector([
        StarsTopupOption(
            stars=1,
            currency="USD",
            amount=MAX_I64,
        ),
        StarsTopupOption(
            stars=2,
            currency="USD",
            amount=-1,
        )
    ])


@handler.on_request(GetContactSignUpNotification, NOBOT_NOAUTH)
async def get_contact_sign_up_notification() -> bool:  # pragma: no cover
    return False


@handler.on_request(SetContactSignUpNotification, NOBOT_NOAUTH)
async def set_contact_sign_up_notification() -> bool:  # pragma: no cover
    return False


@handler.on_request(GetPopularAppBots, NOBOT_NOAUTH)
async def get_popular_app_bots() -> PopularAppBots:
    return PopularAppBots(users=[])


@handler.on_request(GetChannelRestrictedStatusEmojis, NOBOT_NOAUTH)
async def get_channel_restricted_status_emojis() -> EmojiList:
    return EmojiList(hash=0, document_id=[])
