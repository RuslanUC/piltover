from piltover.high_level import MessageHandler
from piltover.tl.functions.channels import GetChannelRecommendations
from piltover.tl.types.messages import Chats

handler = MessageHandler("channels")


@handler.on_request(GetChannelRecommendations)
async def get_channel_recommendations():
    return Chats(chats=[])
