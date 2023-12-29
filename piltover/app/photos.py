from piltover.app.utils import auth_required
from piltover.db.models import User
from piltover.server import MessageHandler, Client
from piltover.tl.types import CoreMessage
from piltover.tl_new.functions.photos import GetUserPhotos
from piltover.tl_new.types.photos import Photos

handler = MessageHandler("photos")


# noinspection PyUnusedLocal
@handler.on_message(GetUserPhotos)
@auth_required
async def get_user_photos(client: Client, request: CoreMessage[GetUserPhotos], session_id: int, user: User):
    return Photos(
        photos=[],
        users=[user],
    )
