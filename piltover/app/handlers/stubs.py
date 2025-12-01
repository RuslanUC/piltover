from piltover.enums import ReqHandlerFlags
from piltover.tl.functions.channels import GetSponsoredMessages_133
from piltover.tl.functions.messages import GetSponsoredMessages
from piltover.tl.functions.premium import GetBoostsStatus, GetMyBoosts
from piltover.tl.types.messages import SponsoredMessages, SponsoredMessagesEmpty
from piltover.tl.types.premium import BoostsStatus, MyBoosts
from piltover.worker import MessageHandler

handler = MessageHandler("stubs")


@handler.on_request(GetBoostsStatus, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_boosts_status() -> BoostsStatus:  # pragma: no cover
    return BoostsStatus(
        level=3,
        current_level_boosts=100,
        boosts=100,
        boost_url="http://127.0.0.1"
    )


@handler.on_request(GetSponsoredMessages_133, ReqHandlerFlags.AUTH_NOT_REQUIRED)
@handler.on_request(GetSponsoredMessages, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_sponsored_messages() -> SponsoredMessages | SponsoredMessagesEmpty:  # pragma: no cover
    return SponsoredMessagesEmpty()


@handler.on_request(GetMyBoosts, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_my_boosts() -> MyBoosts:
    return MyBoosts(my_boosts=[], chats=[], users=[])
