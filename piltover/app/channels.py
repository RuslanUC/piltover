from piltover.high_level import MessageHandler, Client
from piltover.tl_new.functions.channels import GetChannelRecommendations
from piltover.tl_new.types.messages import Chats

handler = MessageHandler("channels")


# noinspection PyUnusedLocal
@handler.on_request(GetChannelRecommendations)
async def get_channel_recommendations(client: Client, request: GetChannelRecommendations):
    return Chats(chats=[])
