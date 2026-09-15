from time import time
from typing import cast
from uuid import UUID

import magic
from loguru import logger
from tortoise.expressions import Q
from tortoise.functions import Sum
from tortoise.transactions import in_transaction

from piltover.app.utils.utils import PHOTOSIZE_TO_INT, MIME_TO_TL
from piltover.config import APP_CONFIG
from piltover.context import request_ctx
from piltover.db.enums import PeerType, FileType
from piltover.db.models import File, Peer, Stickerset, UploadingFileSmall, UploadingFileSmallPart, UploadingFileBig, \
    UploadingFileBigPart
from piltover.enums import ReqHandlerFlags
from piltover.exceptions import ErrorRpc, Unreachable
from piltover.tl import InputDocumentFileLocation, InputPhotoFileLocation, InputPeerPhotoFileLocation, \
    InputEncryptedFileLocation, InputStickerSetThumb
from piltover.tl.functions.upload import SaveFilePart, SaveBigFilePart, GetFile
from piltover.tl.types.storage import FileUnknown, FilePartial, FileJpeg
from piltover.tl.types.upload import File as TLFile
from piltover.utils.debug import measure_time
from piltover.worker import MessageHandler

handler = MessageHandler("upload")


@handler.on_request(SaveFilePart, ReqHandlerFlags.DONT_FETCH_USER)
async def save_file_part(request: SaveFilePart, user_id: int) -> bool:
    size = len(request.bytes_)

    if request.file_part < 0 or request.file_part >= APP_CONFIG.upload_small_max_file_parts:
        raise ErrorRpc(error_code=400, error_message="FILE_PART_INVALID")
    if size > 524288:
        raise ErrorRpc(error_code=400, error_message="FILE_PART_TOO_BIG")
    if size == 0:
        raise ErrorRpc(error_code=400, error_message="FILE_PART_EMPTY")

    mime = None
    if request.file_part == 0:
        mime = magic.from_buffer(request.bytes_[:4096], mime=True)
        if mime == "application/octet-stream":
            mime = None
        logger.trace(f"Resolved file mime type from first part: {mime!r}")

    with measure_time("UploadingFileSmall.get_or_create(...)"):
        file, created = await UploadingFileSmall.get_or_create(user_id=user_id, file_id=request.file_id, defaults={
            "mime": mime,
        })
        if not created and request.file_part == 0 and mime is not None:
            await UploadingFileSmall.filter(id=file.id).update(mime=mime)
            file.mime = mime

    if not created:
        total_size = cast(
            int | None,
            await UploadingFileSmallPart.filter(
                file=file,
                part_id__not=request.file_part,
            ).annotate(total_size=Sum("size")).first().values_list("total_size", flat=True)
        ) or 0
        if (total_size + size) > APP_CONFIG.upload_small_file_max_size_kb * 1024:
            raise ErrorRpc(error_code=400, error_message="FILE_PART_INVALID")

    with measure_time("UploadingFileSmallPart.get_or_create"):
        await UploadingFileSmallPart.update_or_create(
            file=file, part_id=request.file_part, defaults={"size": size},
        )

    storage = request_ctx.get().storage
    with measure_time("storage.save_part(...)"):
        await storage.save_small_part(file.physical_id, request.file_part, request.bytes_)

    return True


@handler.on_request(SaveBigFilePart, ReqHandlerFlags.DONT_FETCH_USER)
async def save_big_file_part(request: SaveBigFilePart, user_id: int) -> bool:
    size = len(request.bytes_)

    if request.file_part < 0 or request.file_part >= APP_CONFIG.upload_max_file_parts \
            or request.file_total_parts > APP_CONFIG.upload_max_file_parts:
        raise ErrorRpc(error_code=400, error_message="FILE_PART_INVALID")
    if size > 524288:
        raise ErrorRpc(error_code=400, error_message="FILE_PART_TOO_BIG")
    if request.file_total_parts == 0:  # TODO: is this a correct error?
        raise ErrorRpc(error_code=400, error_message="FILE_PART_INVALID")

    defaults: dict = {
        "total_parts": request.file_total_parts,
    }

    mime = None
    if request.file_part == 0:
        mime = magic.from_buffer(request.bytes_[:4096], mime=True)
        if mime == "application/octet-stream":
            mime = None
        defaults["mime"] = mime
        logger.trace(f"Resolved file mime type from first part: {mime!r}")

    async with in_transaction():
        update_fields = {}
        with measure_time("UploadingFile.get_or_create(...)"):
            file, created = await UploadingFileBig.get_or_create(
                user_id=user_id, file_id=request.file_id, defaults=defaults,
            )
            if not created and request.file_part == 0 and mime is not None:
                update_fields["mime"] = mime
                file.mime = mime

        if file.total_parts > 0:
            if size == 0:
                raise ErrorRpc(error_code=400, error_message="FILE_PART_EMPTY")
            if file.total_parts != request.file_total_parts or request.file_part >= file.total_parts:
                raise ErrorRpc(error_code=400, error_message="FILE_PART_INVALID")
            is_last = request.file_part == (file.total_parts - 1)
        else:
            is_last = request.file_total_parts != -1
            total_parts = request.file_total_parts
            if size > 0:
                total_parts -= 1
            if is_last and request.file_part != total_parts:
                raise ErrorRpc(error_code=400, error_message="FILE_PART_INVALID")
            if not is_last and size == 0:
                raise ErrorRpc(error_code=400, error_message="FILE_PART_EMPTY")
            if is_last:
                update_fields["total_parts"] = total_parts
                file.total_parts = total_parts

        if not is_last and file.part_size == 0:
            update_fields["part_size"] = size
            file.part_size = size
        if update_fields:
            await UploadingFileBig.filter(id=file.id).update(**update_fields)

    if not is_last and size != file.part_size:
        raise ErrorRpc(error_code=400, error_message="FILE_PART_SIZE_CHANGED")
    if not is_last and (size % 1024 != 0 or 524288 % size != 0):
        raise ErrorRpc(error_code=400, error_message="FILE_PART_SIZE_INVALID")

    async with in_transaction():
        with measure_time("UploadingFilePart.get_or_create"):
            part, created = await UploadingFileBigPart.get_or_create(
                file=file, part_id=request.file_part, defaults={"size": size},
            )
            if not created and is_last and part.size != size:
                await UploadingFileBigPart.filter(id=part.id).update(size=size)

    storage = request_ctx.get().storage
    with measure_time("storage.save_part(...)"):
        await storage.save_big_part(file.physical_id, request.file_part, request.bytes_, is_last)

    return True


SUPPORTED_LOCS = (
    InputDocumentFileLocation, InputPhotoFileLocation, InputPeerPhotoFileLocation, InputEncryptedFileLocation,
    InputStickerSetThumb,
)
ONE_MB = 1024 * 1024
ONE_KB = 1024
FOUR_KB = ONE_KB * 4


@handler.on_request(GetFile, ReqHandlerFlags.DONT_FETCH_USER)
async def get_file(request: GetFile, user_id: int) -> TLFile:
    if not isinstance(request.location, SUPPORTED_LOCS):
        raise ErrorRpc(error_code=400, error_message="LOCATION_INVALID")
    if request.limit < 0 or request.limit > ONE_MB:
        raise ErrorRpc(error_code=400, error_message="LIMIT_INVALID")
    if request.offset // ONE_MB != (request.offset + request.limit - 1) // ONE_MB:
        raise ErrorRpc(error_code=400, error_message="LIMIT_INVALID")
    if request.offset < 0:
        raise ErrorRpc(error_code=400, error_message="OFFSET_INVALID")

    check_div = ONE_KB if request.precise else FOUR_KB
    if request.offset % check_div != 0:
        raise ErrorRpc(error_code=400, error_message="OFFSET_INVALID")
    if request.limit % check_div != 0:
        raise ErrorRpc(error_code=400, error_message="LIMIT_INVALID")

    location = request.location
    ctx = request_ctx.get()
    auth_id = cast(int, ctx.auth_id)

    if isinstance(location, InputPeerPhotoFileLocation):
        peer_info = Peer.type_and_id_from_input(user_id, location.peer)
        if peer_info is None:
            raise ErrorRpc(error_code=400, error_message="LOCATION_INVALID")
        peer_type, peer_id = peer_info
        q = Q(id=location.photo_id)
        if peer_type is PeerType.SELF:
            q &= Q(userphotos__user_id=peer_id)
        elif peer_type is PeerType.USER:
            q &= Q(userphotos__user_id=peer_id) | Q(contacts__owner_id=user_id, contacts__target_id=peer_id)
        elif peer_type is PeerType.CHAT:
            q &= Q(chats__id=peer_id)
        elif peer_type is PeerType.CHANNEL:
            q &= Q(channels__id=peer_id)
        else:
            raise ErrorRpc(error_code=400, error_message="LOCATION_INVALID")
    elif isinstance(location, InputEncryptedFileLocation):
        if not File.check_access_hash(user_id, auth_id, location.id, location.access_hash):
            raise ErrorRpc(error_code=400, error_message="LOCATION_INVALID")
        q = Q(id=location.id, type=FileType.ENCRYPTED)
    elif isinstance(location, InputStickerSetThumb):
        set_q = Stickerset.from_input_q(user_id, auth_id, location.stickerset, prefix="stickersetthumbs__set")
        if set_q is None:
            raise ErrorRpc(error_code=400, error_message="LOCATION_INVALID")
        q = Q(id=location.thumb_version) | set_q
    else:
        valid, const = File.is_file_ref_valid(location.file_reference, user_id, location.id)
        if not valid:
            raise ErrorRpc(error_code=400, error_message="FILE_REFERENCE_EXPIRED", reason="file ref is invalid")

        if const:
            q = Q(
                id=location.id,
                type__not=FileType.ENCRYPTED,
                constant_access_hash=location.access_hash,
                constant_file_ref=UUID(bytes=location.file_reference[12:]),
            )
        else:
            if not File.check_access_hash(user_id, auth_id, location.id, location.access_hash):
                raise ErrorRpc(error_code=400, error_message="LOCATION_INVALID")
            q = Q(id=location.id, type__not=FileType.ENCRYPTED)

    file = await File.get_or_none(q).only("size", "photo_sizes", "mime_type", "physical_id", "created_at")
    if file is None:
        if isinstance(location, InputStickerSetThumb):
            raise ErrorRpc(error_code=400, error_message="LOCATION_INVALID")
        else:
            raise ErrorRpc(error_code=400, error_message="FILE_REFERENCE_EXPIRED", reason="file is None")

    if request.offset >= file.size:
        return TLFile(type_=FilePartial(), mtime=int(time()), bytes_=b"")

    document_thumb = isinstance(location, InputDocumentFileLocation) and location.thumb_size

    storage = ctx.storage
    component = storage.documents

    suffix = None
    if isinstance(location, (InputPhotoFileLocation, InputPeerPhotoFileLocation, InputStickerSetThumb)) \
            or document_thumb:
        if not file.photo_sizes:
            raise ErrorRpc(error_code=400, error_message="LOCATION_INVALID")  # not a photo or does not have thumbs
        if isinstance(location, (InputPhotoFileLocation, InputDocumentFileLocation)):
            size = PHOTOSIZE_TO_INT[location.thumb_size]
        elif isinstance(location, InputStickerSetThumb):
            size = 100
        elif isinstance(location, InputPeerPhotoFileLocation):
            size = 640 if location.big else 160
        else:
            raise Unreachable

        available = [size_["w"] for size_ in file.photo_sizes]
        if size not in available:
            size = min(available, key=lambda x: abs(x - size))
        suffix = str(size)
        component = storage.photos

    with measure_time("storage.<component>.get_part()"):
        data = await component.get_part(file.physical_id, request.offset, request.limit, suffix)
    data = data or b""

    if isinstance(location, (InputPhotoFileLocation, InputPeerPhotoFileLocation, InputStickerSetThumb)) \
            or document_thumb:
        file_type = FileJpeg()
    elif len(data) != file.size:
        file_type = FilePartial()
    else:
        file_type = MIME_TO_TL.get(file.mime_type, FileUnknown())

    return TLFile(type_=file_type, mtime=int(file.created_at.timestamp()), bytes_=data)
