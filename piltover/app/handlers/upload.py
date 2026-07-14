from time import time
from typing import cast, Any
from uuid import UUID

import magic
from loguru import logger
from tortoise.expressions import Q

from piltover.app.utils.utils import PHOTOSIZE_TO_INT, MIME_TO_TL
from piltover.context import request_ctx
from piltover.db.enums import PeerType, FileType
from piltover.db.models import UploadingFile, UploadingFilePart, File, Peer, Stickerset
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
@handler.on_request(SaveBigFilePart, ReqHandlerFlags.DONT_FETCH_USER)
async def save_file_part(request: SaveFilePart | SaveBigFilePart, user_id: int) -> bool:
    size = len(request.bytes_)
    if size > 524288:
        raise ErrorRpc(error_code=400, error_message="FILE_PART_TOO_BIG")
    if request.file_part > 0 and size == 0:
        # TODO: empty parts are allowed when uploading last part of streaming upload:
        #  https://core.telegram.org/api/files#uploading-files
        #  "If the stream ends and the length of the buffered part is equal to 0, upload it anyway"
        raise ErrorRpc(error_code=400, error_message="FILE_PART_EMPTY")

    defaults: dict[str, Any] = {"part_size": size}
    if isinstance(request, SaveBigFilePart):
        defaults["total_parts"] = request.file_total_parts

    mime = None
    if request.file_part == 0 and request.bytes_:
        mime = magic.from_buffer(request.bytes_, mime=True)
        if mime == "application/octet-stream":
            mime = None
        defaults["mime"] = mime
        logger.trace(f"Resolved file mime type from first part: {mime!r}")

    if request.file_part == 0:
        last_part = None
        file, created = await UploadingFile.get_or_create(user_id=user_id, file_id=request.file_id, defaults=defaults)
        if not created and file.mime is None and mime is not None:
            file.mime = mime
            await file.save(update_fields=["mime"])
    else:
        last_part = await UploadingFilePart.get_or_none(
            file_id=request.file_id, part_id=request.file_part - 1, file__user_id=user_id,
        ).select_related("file")
        if last_part is None:
            raise ErrorRpc(error_code=400, error_message="FILE_PART_INVALID")
        file = last_part.file
        if last_part.size != file.part_size or last_part.size % 1024 != 0:
            raise ErrorRpc(error_code=400, error_message="FILE_PART_INVALID")

    if file.total_parts > 0:
        if not isinstance(request, SaveBigFilePart):
            raise ErrorRpc(error_code=400, error_message="FILE_PART_INVALID")
        if file.total_parts != request.file_total_parts or request.file_part >= file.total_parts:
            raise ErrorRpc(error_code=400, error_message="FILE_PART_INVALID")

    if last_part is not None \
            and size != last_part.size \
            and await UploadingFilePart.filter(file=file, part_id=request.file_part + 1).exists():
        raise ErrorRpc(error_code=400, error_message="FILE_PART_SIZE_INVALID")

    with measure_time("<create part>"):
        part, created = await UploadingFilePart.get_or_create(
            file=file, part_id=request.file_part, defaults={"size": size},
        )
        if size != part.size:
            raise ErrorRpc(error_code=400, error_message="FILE_PART_SIZE_INVALID")

    storage = request_ctx.get().storage
    with measure_time("storage.save_part(...)"):
        await storage.save_part(file.physical_id, request.file_part, request.bytes_)

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
        if peer_type in (PeerType.SELF, PeerType.USER):
            q &= Q(userphotos__user_id=peer_id)
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

    with measure_time(f"storage.<component>.get_part()"):
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
