from piltover.app import user
from piltover.server import MessageHandler, Client
from piltover.tl.types import CoreMessage
from piltover.tl_new.functions.photos import GetUserPhotos
from piltover.tl_new.types.photos import Photos

handler = MessageHandler("photos")


# noinspection PyUnusedLocal
@handler.on_message(GetUserPhotos)
async def get_user_photos(client: Client, request: CoreMessage[GetUserPhotos], session_id: int):
    return Photos(
        photos=[],
        users=[user],
    )
