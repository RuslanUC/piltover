from piltover.app.utils.utils import upload_file, resize_photo, generate_stripped
from piltover.db.models import User, UserPhoto, Peer
from piltover.enums import ReqHandlerFlags
from piltover.exceptions import ErrorRpc
from piltover.high_level import MessageHandler
from piltover.tl import InputPhoto, Long, Vector
from piltover.tl.functions.photos import GetUserPhotos, UploadProfilePhoto, DeletePhotos
from piltover.tl.types.photos import Photos, Photo as PhotosPhoto

handler = MessageHandler("photos")


@handler.on_request(GetUserPhotos, ReqHandlerFlags.AUTH_REQUIRED)
async def get_user_photos(request: GetUserPhotos, user: User):
    if (peer := await Peer.from_input_peer(user, request.user_id)) is None:
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    photos = await UserPhoto.filter(user=peer.user).select_related("file").order_by("-id")

    return Photos(
        photos=[await photo.to_tl(user) for photo in photos],
        users=[await peer.user.to_tl(user)],
    )


@handler.on_request(UploadProfilePhoto, ReqHandlerFlags.AUTH_REQUIRED)
async def upload_profile_photo(request: UploadProfilePhoto, user: User):
    if request.file is None:
        raise ErrorRpc(error_code=400, error_message="PHOTO_FILE_MISSING")

    file = await upload_file(user, request.file, "image/png", [])
    sizes = await resize_photo(str(file.physical_id))
    stripped = await generate_stripped(str(file.physical_id))
    await file.update(attributes=file.attributes | {"_sizes": sizes, "_size_stripped": stripped.hex()})
    await UserPhoto.filter(user=user).update(current=False)
    photo = await UserPhoto.create(current=True, file=file, user=user)

    #update = UpdateUser(user_id=user.id)
    #await UpdatesManager().write_update(user, update)

    return PhotosPhoto(
        photo=await photo.to_tl(user),
        users=[],  # [await user.to_tl(user)],
    )


@handler.on_request(DeletePhotos, ReqHandlerFlags.AUTH_REQUIRED)
async def delete_photos(request: DeletePhotos, user: User):
    deleted = Vector(value_type=Long)

    for photo in request.id:
        if not isinstance(photo, InputPhoto):
            continue
        if not (photo := await UserPhoto.get_or_none(id=photo.id, user=user)):
            continue

        await photo.delete()
        deleted.append(photo.id)

    return deleted
