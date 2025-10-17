import piltover.app.utils.updates_manager as upd
from piltover.context import request_ctx
from piltover.db.enums import PrivacyRuleKeyType, FileType
from piltover.db.models import User, UserPhoto, Peer, UploadingFile, PrivacyRule
from piltover.exceptions import ErrorRpc
from piltover.tl import InputPhoto, InputPhotoEmpty, PhotoEmpty, LongVector
from piltover.tl.functions.photos import GetUserPhotos, UploadProfilePhoto, DeletePhotos, UpdateProfilePhoto
from piltover.tl.types.photos import Photos, Photo as PhotosPhoto
from piltover.worker import MessageHandler

handler = MessageHandler("photos")


@handler.on_request(GetUserPhotos)
async def get_user_photos(request: GetUserPhotos, user: User):
    peer = await Peer.from_input_peer_raise(user, request.user_id)
    peer_user = peer.peer_user(user)

    if not await PrivacyRule.has_access_to(user, peer_user, PrivacyRuleKeyType.PROFILE_PHOTO):
        return Photos(photos=[], users=[])

    photos = await UserPhoto.filter(user=peer_user).select_related("file").order_by("-id")

    return Photos(
        photos=[await photo.to_tl(user) for photo in photos],
        users=[await peer_user.to_tl(user)],
    )


@handler.on_request(UploadProfilePhoto)
async def upload_profile_photo(request: UploadProfilePhoto, user: User):
    if request.file is None:
        raise ErrorRpc(error_code=400, error_message="PHOTO_FILE_MISSING")

    uploaded_file = await UploadingFile.get_or_none(user=user, file_id=request.file.id)
    if uploaded_file is None:
        raise ErrorRpc(error_code=400, error_message="INPUT_FILE_INVALID")
    if uploaded_file.mime is None or not uploaded_file.mime.startswith("image/"):
        raise ErrorRpc(error_code=400, error_message="INPUT_FILE_INVALID")

    storage = request_ctx.get().storage
    file = await uploaded_file.finalize_upload(storage, "image/png", file_type=FileType.PHOTO)
    await UserPhoto.filter(user=user).update(current=False)
    photo = await UserPhoto.create(current=True, file=file, user=user)

    await upd.update_user(user)

    return PhotosPhoto(
        photo=await photo.to_tl(user),
        users=[],  # [await user.to_tl(user)],
    )


@handler.on_request(DeletePhotos)
async def delete_photos(request: DeletePhotos, user: User):
    deleted = LongVector()

    for photo in request.id:
        if not isinstance(photo, InputPhoto):
            continue
        if not (photo := await UserPhoto.get_or_none(id=photo.id, user=user)):
            continue

        await photo.delete()
        deleted.append(photo.id)

    if deleted:
        await upd.update_user(user)

    return deleted


@handler.on_request(UpdateProfilePhoto)
async def update_profile_photo(request: UpdateProfilePhoto, user: User):
    photo = None
    if isinstance(request.id, InputPhotoEmpty):
        await UserPhoto.filter(user=user).delete()
    elif (photo := await UserPhoto.get_or_none(id=request.id.id, user=user)) is not None:
        await UserPhoto.filter(user=user).update(current=False)
        photo.current = True
        await photo.save(update_fields=["current"])

    await upd.update_user(user)

    return PhotosPhoto(
        photo=await photo.to_tl(user) if photo else PhotoEmpty(id=0),
        users=[],  # [await user.to_tl(user)],
    )
