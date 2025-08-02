from uuid import UUID

from fastrand import xorshift128plus_bytes
from loguru import logger
from tortoise.expressions import Q, F
from tortoise.transactions import in_transaction

from piltover.app.utils.utils import telegram_hash
from piltover.db.enums import FileType
from piltover.db.models import User, Stickerset, FileAccess, File
from piltover.exceptions import ErrorRpc
from piltover.tl import Long, StickerSetCovered, StickerSetNoCovered
from piltover.tl.functions.messages import GetMyStickers, GetStickerSet
from piltover.tl.functions.stickers import CreateStickerSet, CheckShortName, ChangeStickerPosition, RenameStickerSet, \
    DeleteStickerSet, ChangeSticker
from piltover.tl.types.messages import StickerSet as MessagesStickerSet, MyStickers, StickerSetNotModified
from piltover.worker import MessageHandler

handler = MessageHandler("messages.stickers")


ord_a = ord("a")
ord_z = ord("z")
ord_0 = ord("0")
ord_9 = ord("9")


@handler.on_request(CheckShortName)
async def check_stickerset_short_name(request: CheckShortName, prefix: str = "") -> bool:
    if not request.short_name or len(request.short_name) > 64:
        raise ErrorRpc(error_code=400, error_message=f"{prefix}SHORT_NAME_INVALID")

    short_name = request.short_name.lower()
    if ord(short_name[0]) < ord_a or ord(short_name[0]) > ord_z:
        raise ErrorRpc(error_code=400, error_message=f"{prefix}SHORT_NAME_INVALID")

    if not all(ord_0 <= ord(char) <= ord_9 or ord_a <= ord(char) <= ord_z for char in short_name) or "__" in short_name:
        raise ErrorRpc(error_code=400, error_message=f"{prefix}SHORT_NAME_INVALID")

    if await Stickerset.filter(short_name=request.short_name).exists():
        raise ErrorRpc(error_code=400, error_message=f"{prefix}SHORT_NAME_OCCUPIED")

    return True


@handler.on_request(CreateStickerSet)
async def create_sticker_set(request: CreateStickerSet, user: User) -> MessagesStickerSet:
    if not request.title or len(request.title) > 64:
        raise ErrorRpc(error_code=400, error_message="PACK_TITLE_INVALID")

    await check_stickerset_short_name(CheckShortName(short_name=request.short_name), user, "PACK_")

    if not request.stickers:
        raise ErrorRpc(error_code=400, error_message="STICKERS_EMPTY")

    # TODO: validate emojis

    files_q = Q()

    for input_sticker in request.stickers:
        input_doc = input_sticker.document
        valid, const = FileAccess.is_file_ref_valid(input_doc.file_reference, user.id, input_doc.id)
        if not valid:
            raise ErrorRpc(error_code=400, error_message="STICKER_FILE_INVALID")

        base_q = Q(id=input_doc.id, type=FileType.DOCUMENT_STICKER)
        if const:
            files_q |= base_q & Q(
                constant_access_hash=input_doc.access_hash, constant_file_ref=input_doc.file_reference,
            )
        else:
            files_q |= base_q & Q(
                fileaccesss__user=user, fileaccesss__access_hash=input_doc.access_hash,
            )

    files = {file.id: file for file in await File.filter(files_q)}
    files_to_create = []

    for input_sticker in request.stickers:
        file = files.get(input_sticker.document.id)
        if file is None:
            raise ErrorRpc(error_code=400, error_message="STICKER_FILE_INVALID")

        # TODO: support video, animated and tgs stickers
        if file.mime_type != "image/png":
            raise ErrorRpc(error_code=400, error_message="STICKER_PNG_NOPNG")

        dims = (file.width, file.height)
        if 512 not in dims or any(dim > 512 for dim in dims):
            raise ErrorRpc(error_code=400, error_message="STICKER_PNG_DIMENSIONS")

        if file.size > 512 * 1024:
            raise ErrorRpc(error_code=400, error_message="STICKER_FILE_INVALID")

    # TODO: thumbs

    stickerset = await Stickerset.create(
        title=request.title,
        short_name=request.short_name,
        owner=None,
    )

    for idx, input_sticker in enumerate(request.stickers):
        file = files[input_sticker.document.id]
        files_to_create.append(File(
            physical_id=file.physical_id,
            created_at=file.created_at,
            mime_type=file.mime_type,
            size=file.size,
            type=FileType.DOCUMENT_STICKER,
            constant_access_hash=Long.from_bytes(xorshift128plus_bytes(8)),
            constant_file_ref=UUID(xorshift128plus_bytes(16)),
            filename=file.filename,
            stickerset=stickerset,
            sticker_pos=idx,
            sticker_alt=input_sticker.emoji,
        ))

    try:
        await File.bulk_create(files_to_create)
    except Exception as e:
        logger.opt(exception=e).error("Failed to create stickerset files")
        await stickerset.delete()
        raise

    stickerset.owner = user
    stickerset.hash = telegram_hash(stickerset.gen_for_hash(await stickerset.documents_query()), 32)
    await stickerset.save(update_fields=["owner_id", "hash"])

    return await stickerset.to_tl_messages(user)


@handler.on_request(ChangeStickerPosition)
async def change_sticker_position(request: ChangeStickerPosition, user: User) -> MessagesStickerSet:
    doc = request.sticker
    valid, const = FileAccess.is_file_ref_valid(doc.file_reference, user.id, doc.id)
    if not valid or not const:
        raise ErrorRpc(error_code=400, error_message="STICKER_INVALID")

    file = await File.get_or_none(
        id=request.sticker.id, constant_access_hash=doc.access_hash, constant_file_ref=doc.file_reference,
        stickerset__owner=user,
    ).select_related("stickerset")

    if file is None:
        raise ErrorRpc(error_code=400, error_message="STICKER_INVALID")

    stickerset = file.stickerset

    min_pos = 0
    max_pos = await stickerset.documents_query().count() - 1
    new_pos = max(min_pos, min(max_pos, request.position))
    old_pos = request.position

    if old_pos == new_pos:
        return await stickerset.to_tl_messages(user)

    # if sticker position is, for example, 5, new position is 10 and there is 15 stickers, then we need to:
    #  1) subtract 1 from stickers with positions 6-10 (current_pos + 1, new_pos)
    #  2) change sticker position from 5 to 10
    # if sticker position is, for example, 10, new position is 5 and there is 15 stickers, then we need to:
    #  1) add 1 to stickers with positions 5-9 (new_pos, current_pos - 1)
    #  2) change sticker position from 10 to 5

    file.sticker_pos = new_pos
    if new_pos > old_pos:
        update_query = File.filter(stickerset=stickerset, sticker_pos__gt=old_pos, sticker_pos__lte=new_pos).update(sticker_pos=F("sticker_pos") - 1)
    else:
        update_query = File.filter(stickerset=stickerset, sticker_pos__gte=new_pos, sticker_pos__lt=old_pos).update(sticker_pos=F("sticker_pos") + 1)

    async with in_transaction():
        await update_query
        await file.save(update_fields=["sticker_pos"])

    stickerset.hash = telegram_hash(stickerset.gen_for_hash(await stickerset.documents_query()), 32)
    await stickerset.save(update_fields=["hash"])

    return await stickerset.to_tl_messages(user)


@handler.on_request(RenameStickerSet)
async def rename_stickerset(request: RenameStickerSet, user: User) -> MessagesStickerSet:
    stickerset = await Stickerset.from_input(request.stickerset)
    if stickerset is None or stickerset.owner_id != user.id:
        raise ErrorRpc(error_code=400, error_message="STICKERSET_INVALID")

    if not request.title or len(request.title) > 64:
        raise ErrorRpc(error_code=400, error_message="STICKERSET_INVALID")

    stickerset.title = request.title
    stickerset.hash = telegram_hash(stickerset.gen_for_hash(await stickerset.documents_query()), 32)
    await stickerset.save(update_fields=["title", "hash"])

    return await stickerset.to_tl_messages(user)


@handler.on_request(DeleteStickerSet)
async def delete_stickerset(request: DeleteStickerSet, user: User) -> bool:
    stickerset = await Stickerset.from_input(request.stickerset)
    if stickerset is None or stickerset.owner_id != user.id:
        raise ErrorRpc(error_code=400, error_message="STICKERSET_INVALID")

    await stickerset.delete()

    return True


@handler.on_request(GetMyStickers)
async def get_my_stickers(request: GetMyStickers, user: User) -> MyStickers:
    limit = max(1, min(50, request.limit))
    stickersets = await Stickerset.filter(owner=user, id__lt=request.offset_id).order_by("-id").limit(limit)
    covers = {file.stickerset_id: file for file in await File.filter(stickerset__in=stickersets, sticker_pos=0)}

    result = []
    for stickerset in stickersets:
        if stickerset.id in covers:
            result.append(StickerSetCovered(
                set=await stickerset.to_tl(user),
                cover=await covers[stickerset.id].to_tl_document(user),
            ))
        else:
            result.append(StickerSetNoCovered(
                set=await stickerset.to_tl(user),
            ))

    return MyStickers(
        sets=result,
        count=await Stickerset.filter(owner=user).count(),
    )


@handler.on_request(ChangeSticker)
async def change_sticker(request: ChangeSticker, user: User) -> MessagesStickerSet:
    doc = request.sticker
    valid, const = FileAccess.is_file_ref_valid(doc.file_reference, user.id, doc.id)
    if not valid or not const:
        raise ErrorRpc(error_code=400, error_message="STICKER_INVALID")

    file = await File.get_or_none(
        id=request.sticker.id, constant_access_hash=doc.access_hash, constant_file_ref=doc.file_reference,
        stickerset__owner=user,
    ).select_related("stickerset")

    if file is None:
        raise ErrorRpc(error_code=400, error_message="STICKER_INVALID")

    stickerset = file.stickerset

    # TODO: mask coords and keywords
    if request.emoji is None or request.emoji == file.sticker_alt:
        return await stickerset.to_tl_messages(user)

    file.sticker_alt = request.emoji
    await file.save(update_fields=["sticker_alt"])

    stickerset.hash = telegram_hash(stickerset.gen_for_hash(await stickerset.documents_query()), 32)
    await stickerset.save(update_fields=["hash"])

    return await stickerset.to_tl_messages(user)


@handler.on_request(GetStickerSet)
async def get_stickerset(request: GetStickerSet, user: User) -> MessagesStickerSet | StickerSetNotModified:
    stickerset = await Stickerset.from_input(request.stickerset)
    if stickerset is None:
        raise ErrorRpc(error_code=406, error_message="STICKERSET_INVALID")

    if request.hash == stickerset.hash:
        return StickerSetNotModified()

    return await stickerset.to_tl_messages(user)


# working with stickersets:
# TODO: ReplaceSticker
# TODO: AddStickerToSet
# TODO: SetStickerSetThumb
# TODO: RemoveStickerFromSet
# TODO: GetStickers

# working with recent stickers:
# TODO: GetRecentStickers
# TODO: ClearRecentStickers
# TODO: SaveRecentSticker

# working with installed sets:
# TODO: GetAllStickers
# TODO: InstallStickerSet
# TODO: UninstallStickerSet
# TODO: ReorderStickerSets
# TODO: GetArchivedStickers
# TODO: ToggleStickerSets

# working with faved stickers:
# TODO: FaveSticker
# TODO: GetFavedStickers
