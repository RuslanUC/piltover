from uuid import UUID

from fastrand import xorshift128plus_bytes
from loguru import logger
from tortoise.expressions import Q

from piltover.app.utils.utils import telegram_hash
from piltover.db.enums import FileType
from piltover.db.models import User, Stickerset, FileAccess, File
from piltover.exceptions import ErrorRpc
from piltover.tl import Long
from piltover.tl.functions.stickers import CreateStickerSet, CheckShortName
from piltover.tl.types.messages import StickerSet as MessagesStickerSet
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
    stickerset.hash = telegram_hash((file.id for file in await stickerset.documents_query()), 32)
    await stickerset.save(update_fields=["owner_id"])

    return await stickerset.to_tl_messages(user)


