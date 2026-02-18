from piltover.enums import ReqHandlerFlags
from piltover.tl import StarsAmount, TLObjectVector, StarsTopupOption
from piltover.tl.functions.account import GetCollectibleEmojiStatuses
from piltover.tl.functions.channels import GetSponsoredMessages_133
from piltover.tl.functions.messages import GetSponsoredMessages
from piltover.tl.functions.payments import GetStarsStatus, GetStarsSubscriptions, GetStarsTransactions, \
    GetStarsTopupOptions
from piltover.tl.functions.premium import GetBoostsStatus, GetMyBoosts, GetBoostsList
from piltover.tl.types.account import EmojiStatuses
from piltover.tl.types.messages import SponsoredMessages, SponsoredMessagesEmpty
from piltover.tl.types.payments import StarsStatus
from piltover.tl.types.premium import BoostsStatus, MyBoosts, BoostsList
from piltover.worker import MessageHandler

handler = MessageHandler("stubs")

MAX_I32 = 2 ** 31 - 1
MAX_I64 = 2 ** 63 - 1


@handler.on_request(GetBoostsStatus, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_boosts_status() -> BoostsStatus:  # pragma: no cover
    return BoostsStatus(
        level=3,
        current_level_boosts=MAX_I32,
        boosts=MAX_I32,
        boost_url="http://127.0.0.1"
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
