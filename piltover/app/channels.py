from piltover.high_level import MessageHandler, Client
from piltover.tl.functions.channels import GetChannelRecommendations
from piltover.tl.types.messages import Chats

handler = MessageHandler("channels")


# noinspection PyUnusedLocal
@handler.on_request(GetChannelRecommendations)
async def get_channel_recommendations(client: Client, request: GetChannelRecommendations):
    return Chats(chats=[])
