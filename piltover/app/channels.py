from piltover.server import MessageHandler, Client
from piltover.tl.types import CoreMessage
from piltover.tl_new.functions.channels import GetChannelRecommendations
from piltover.tl_new.types.messages import Chats

handler = MessageHandler("channels")


# noinspection PyUnusedLocal
@handler.on_message(GetChannelRecommendations)
async def get_channel_recommendations(client: Client, request: CoreMessage[GetChannelRecommendations], session_id: int):
    return Chats(chats=[])
