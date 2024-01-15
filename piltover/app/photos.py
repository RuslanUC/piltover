from piltover.app.utils import upload_file, resize_photo
from piltover.db.models import User, UserPhoto
from piltover.exceptions import ErrorRpc
from piltover.high_level import MessageHandler, Client
from piltover.tl_new import InputUser, InputUserEmpty, InputUserSelf
from piltover.tl_new.functions.photos import GetUserPhotos, UploadProfilePhoto
from piltover.tl_new.types.photos import Photos, Photo as PhotosPhoto

handler = MessageHandler("photos")


# noinspection PyUnusedLocal
@handler.on_request(GetUserPhotos, True)
async def get_user_photos(client: Client, request: GetUserPhotos, user: User):
    if isinstance(request.user_id, InputUserSelf):
        target_user = user
    elif isinstance(request.user_id, InputUser):
        if request.user_id.user_id == user.id:
            target_user = user
        elif (target_user := await User.get_or_none(id=request.user_id.user_id)) is None:
            raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")
    elif isinstance(request.user_id, InputUserEmpty):
        return Photos(
            photos=[],
            users=[],
        )
    else:
        raise ErrorRpc(error_code=400, error_message="PEER_ID_NOT_SUPPORTED")

    photos = await UserPhoto.filter(user=target_user).select_related("file")

    return Photos(
        photos=[await photo.to_tl(user) for photo in photos],
        users=[await target_user.to_tl(user)],
    )


# noinspection PyUnusedLocal
@handler.on_request(UploadProfilePhoto, True)
async def upload_profile_photo(client: Client, request: UploadProfilePhoto, user: User):
    if request.file is None:
        raise ErrorRpc(error_code=400, error_message="PHOTO_FILE_MISSING")

    file = await upload_file(user, request.file, "image/png", [])
    sizes = await resize_photo(str(file.physical_id))
    await file.update(attributes=file.attributes | {"_sizes": sizes})
    await UserPhoto.filter(user=user).update(current=False)
    photo = await UserPhoto.create(current=True, file=file, user=user)

    return PhotosPhoto(
        photo=await photo.to_tl(user),
        users=[],  # [await user.to_tl(user)],
    )
