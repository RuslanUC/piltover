from piltover.enums import ReqHandlerFlags
from piltover.high_level import MessageHandler
from piltover.tl.functions.channels import GetChannelRecommendations, GetAdminedPublicChannels
from piltover.tl.types.messages import Chats

handler = MessageHandler("channels")


@handler.on_request(GetChannelRecommendations, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_channel_recommendations():
    return Chats(chats=[])


@handler.on_request(GetAdminedPublicChannels, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_admined_public_channels():
    return Chats(chats=[])
