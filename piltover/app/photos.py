from piltover.app.utils import upload_file, resize_photo
from piltover.db.models import User, UserPhoto
from piltover.enums import ReqHandlerFlags
from piltover.exceptions import ErrorRpc
from piltover.high_level import MessageHandler, Client
from piltover.tl_new import InputPhoto, Long, Vector
from piltover.tl_new.functions.photos import GetUserPhotos, UploadProfilePhoto, DeletePhotos
from piltover.tl_new.types.photos import Photos, Photo as PhotosPhoto

handler = MessageHandler("photos")


# noinspection PyUnusedLocal
@handler.on_request(GetUserPhotos, ReqHandlerFlags.AUTH_REQUIRED)
async def get_user_photos(client: Client, request: GetUserPhotos, user: User):
    if (target_user := await User.from_input_peer(request.user_id, user)) is None:
        raise ErrorRpc(error_code=400, error_message="USER_ID_INVALID")

    photos = await UserPhoto.filter(user=target_user).select_related("file").order_by("-id")

    return Photos(
        photos=[await photo.to_tl(user) for photo in photos],
        users=[await target_user.to_tl(user)],
    )


# noinspection PyUnusedLocal
@handler.on_request(UploadProfilePhoto, ReqHandlerFlags.AUTH_REQUIRED)
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


# noinspection PyUnusedLocal
@handler.on_request(DeletePhotos, ReqHandlerFlags.AUTH_REQUIRED)
async def delete_photos(client: Client, request: DeletePhotos, user: User):
    deleted = Vector(value_type=Long)

    for photo in request.id:
        if not isinstance(photo, InputPhoto):
            continue
        if not (photo := await UserPhoto.get_or_none(id=photo.id, user=user)):
            continue

        await photo.delete()
        deleted.append(photo.id)

    return deleted
