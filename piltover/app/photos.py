from piltover.db.models import User
from piltover.high_level import MessageHandler, Client
from piltover.tl_new.functions.photos import GetUserPhotos
from piltover.tl_new.types.photos import Photos

handler = MessageHandler("photos")


# noinspection PyUnusedLocal
@handler.on_request(GetUserPhotos, True)
async def get_user_photos(client: Client, request: GetUserPhotos, user: User):
    return Photos(
        photos=[],
        users=[user.to_tl(user)],
    )
