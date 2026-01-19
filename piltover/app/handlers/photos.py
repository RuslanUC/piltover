from tortoise.expressions import Subquery
from tortoise.transactions import in_transaction

import piltover.app.utils.updates_manager as upd
from piltover.context import request_ctx
from piltover.db.enums import PrivacyRuleKeyType, FileType, PeerType
from piltover.db.models import User, UserPhoto, Peer, UploadingFile, PrivacyRule, Bot
from piltover.enums import ReqHandlerFlags
from piltover.exceptions import ErrorRpc
from piltover.tl import InputPhoto, InputPhotoEmpty, PhotoEmpty, LongVector, InputUser
from piltover.tl.functions.photos import GetUserPhotos, UploadProfilePhoto, DeletePhotos, UpdateProfilePhoto
from piltover.tl.types.photos import Photos, Photo as PhotosPhoto, PhotosSlice
from piltover.worker import MessageHandler

handler = MessageHandler("photos")


@handler.on_request(GetUserPhotos)
async def get_user_photos(request: GetUserPhotos, user: User):
    peer = await Peer.from_input_peer_raise(user, request.user_id)
    peer_user = peer.peer_user(user)

    if not await PrivacyRule.has_access_to(user, peer_user, PrivacyRuleKeyType.PROFILE_PHOTO):
        return Photos(photos=[], users=[])

    limit = min(100, max(request.limit, 1))
    photos_query = UserPhoto.filter(user=peer_user, fallback=False).select_related("file")

    photos = []
    if request.offset < 0:
        photos_query_neg = photos_query
        if request.max_id:
            photos_query_neg = photos_query.filter(id__gte=request.max_id)
        photos.extend(reversed(await photos_query_neg.limit(limit).order_by("id")))
        limit -= len(photos)
    elif request.offset > 0:
        photos_query = photos_query.offset(request.offset)

    if request.max_id:
        photos_query = photos_query.filter(id__lt=request.max_id)

    if limit:
        photos.extend(await photos_query.limit(limit).order_by("-id"))

    photos_total = await UserPhoto.filter(user=peer_user, fallback=False).count()
    photos_tl = [photo.to_tl() for photo in photos]
    users_tl = [await peer_user.to_tl()]

    if photos_total >= len(photos):
        return PhotosSlice(
            count=photos_total,
            photos=photos_tl,
            users=users_tl,
        )

    return Photos(
        photos=photos_tl,
        users=users_tl,
    )


async def _current_user_or_bot(input_bot: InputUser, user: User) -> User:
    if input_bot is None:
        return user

    peer = await Peer.from_input_peer_raise(user, input_bot, "BOT_INVALID")
    if peer.type is not PeerType.USER or not peer.user.bot:
        raise ErrorRpc(error_code=400, error_message="BOT_INVALID")
    if not await Bot.filter(owner=user, bot=peer.user).exists():
        raise ErrorRpc(error_code=400, error_message="BOT_INVALID")
    return peer.user


@handler.on_request(UploadProfilePhoto)
async def upload_profile_photo(request: UploadProfilePhoto, user: User):
    if request.file is None:
        raise ErrorRpc(error_code=400, error_message="PHOTO_FILE_MISSING")

    target_user = await _current_user_or_bot(request.bot, user)

    uploaded_file = await UploadingFile.get_or_none(user=user, file_id=request.file.id)
    if uploaded_file is None:
        raise ErrorRpc(error_code=400, error_message="INPUT_FILE_INVALID")
    if uploaded_file.mime is None or not uploaded_file.mime.startswith("image/"):
        raise ErrorRpc(error_code=400, error_message="INPUT_FILE_INVALID")

    storage = request_ctx.get().storage
    file = await uploaded_file.finalize_upload(
        storage, "image/png", file_type=FileType.PHOTO, profile_photo=True,
    )
    async with in_transaction():
        if target_user.bot:
            await UserPhoto.filter(user=target_user).delete()
            request.fallback = False
        elif not request.fallback:
            await UserPhoto.filter(user=target_user).update(current=False)
        elif request.fallback:
            # TODO: or dont delete and just get latest UserPhoto in GetFullUser?
            await UserPhoto.filter(user=target_user, fallback=True).delete()

        photo = await UserPhoto.create(
            current=not request.fallback,
            fallback=request.fallback,
            file=file,
            user=target_user,
        )

        user.version += 1
        await user.save(update_fields=["version"])

    await upd.update_user(target_user)

    return PhotosPhoto(
        photo=photo.to_tl(),
        users=[],
    )


@handler.on_request(DeletePhotos, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def delete_photos(request: DeletePhotos, user: User):
    deleted = LongVector()

    ids = []

    for photo in request.id:
        if not isinstance(photo, InputPhoto):
            continue
        ids.append(photo.id)

    if not ids:
        return deleted

    async with in_transaction():
        photos = await UserPhoto.select_for_update().filter(user=user, id__in=ids).values_list("id", "current")
        if not photos:
            return deleted

        actual_ids = []
        need_new_current = False
        for photo_id, current in photos:
            actual_ids.append(photo_id)
            if current:
                need_new_current = True

        await UserPhoto.filter(id__in=actual_ids).delete()

        if need_new_current:
            await UserPhoto.filter(id=Subquery(
                UserPhoto.filter(user=user).order_by("-id").first().values_list("id", flat=True)
            )).update(current=True)
            user.version += 1
            await user.save(update_fields=["version"])

    deleted.extend(actual_ids)
    await upd.update_user(user)

    return deleted


@handler.on_request(UpdateProfilePhoto)
async def update_profile_photo(request: UpdateProfilePhoto, user: User):
    target_user = await _current_user_or_bot(request.bot, user)

    photo = None
    if isinstance(request.id, InputPhotoEmpty):
        await UserPhoto.filter(user=target_user, fallback=request.fallback).delete()
    elif (photo := await UserPhoto.get_or_none(id=request.id.id, user=target_user).select_related("file")) is not None:
        async with in_transaction():
            # TODO: figure out what telegram does when request.fallback is set
            if request.fallback:
                if target_user.bot:
                    raise ErrorRpc(error_code=400, error_message="BOT_FALLBACK_UNSUPPORTED")
                await UserPhoto.filter(user=target_user, fallback=True).delete()
                await UserPhoto.create(user=target_user, fallback=True, current=False, file=photo.file)
            else:
                await UserPhoto.filter(user=target_user).update(current=False)
                photo.current = True
                photo.fallback = False
                await photo.save(update_fields=["current", "fallback"])

            target_user.version += 1
            await target_user.save(update_fields=["version"])

    await upd.update_user(target_user)

    return PhotosPhoto(
        photo=photo.to_tl() if photo else PhotoEmpty(id=0),
        users=[],
    )


# TODO: UploadContactProfilePhoto
