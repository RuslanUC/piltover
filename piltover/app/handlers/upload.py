from time import time
from uuid import UUID

import magic
from loguru import logger
from tortoise.expressions import Q

from piltover.app.utils.utils import PHOTOSIZE_TO_INT, MIME_TO_TL
from piltover.context import request_ctx
from piltover.db.enums import PeerType, FileType
from piltover.db.models import User, UploadingFile, UploadingFilePart, File, Peer, Stickerset
from piltover.exceptions import ErrorRpc, Unreachable
from piltover.tl import InputDocumentFileLocation, InputPhotoFileLocation, InputPeerPhotoFileLocation, \
    InputEncryptedFileLocation, InputStickerSetThumb
from piltover.tl.functions.upload import SaveFilePart, SaveBigFilePart, GetFile
from piltover.tl.types.storage import FileUnknown, FilePartial, FileJpeg
from piltover.tl.types.upload import File as TLFile
from piltover.worker import MessageHandler

handler = MessageHandler("upload")


@handler.on_request(SaveFilePart)
@handler.on_request(SaveBigFilePart)
async def save_file_part(request: SaveFilePart | SaveBigFilePart, user: User):
    defaults = {}
    if isinstance(request, SaveBigFilePart):
        defaults["total_parts"] = request.file_total_parts

    mime = None
    if request.file_part == 0 and request.bytes_:
        mime = magic.from_buffer(request.bytes_[:4096], mime=True)
        if mime == "application/octet-stream":
            mime = None
        defaults["mime"] = mime
        logger.trace(f"Resolved file mime type from first part: {mime!r}")

    file, created = await UploadingFile.get_or_create(user=user, file_id=request.file_id, defaults=defaults)
    if not created and request.file_part == 0 and file.mime is None and mime is not None:
        file.mime = mime
        await file.save(update_fields=["mime"])

    last_part = await UploadingFilePart.filter(file=file).order_by("-part_id").first()

    if file.total_parts > 0 and isinstance(request, SaveFilePart):
        raise ErrorRpc(error_code=400, error_message="FILE_PART_INVALID")
    if file.total_parts > 0 and (file.total_parts != request.file_total_parts or request.file_part >= file.total_parts):
        raise ErrorRpc(error_code=400, error_message="FILE_PART_INVALID")

    size = len(request.bytes_)
    if (ex_part := await UploadingFilePart.get_or_none(file=file, part_id=request.file_part)) is not None:
        if size == ex_part.size:
            return True
        raise ErrorRpc(error_code=400, error_message="FILE_PART_INVALID")
    maybe_last = size % 1024 != 0 or 524288 % size != 0
    if maybe_last and last_part is not None and last_part.part_id >= request.file_part:
        raise ErrorRpc(error_code=400, error_message="FILE_PART_SIZE_INVALID")
    if size > 524288:
        raise ErrorRpc(error_code=400, error_message="FILE_PART_TOO_BIG")
    if size == 0:
        raise ErrorRpc(error_code=400, error_message="FILE_PART_EMPTY")

    part, created = await UploadingFilePart.get_or_create(file=file, part_id=request.file_part, defaults={"size": size})
    if not created:
        if part.size == size:
            return True
        raise ErrorRpc(error_code=400, error_message="FILE_PART_INVALID")

    storage = request_ctx.get().storage
    await storage.save_part(file.physical_id, request.file_part, request.bytes_, maybe_last)

    return True


SUPPORTED_LOCS = (
    InputDocumentFileLocation, InputPhotoFileLocation, InputPeerPhotoFileLocation, InputEncryptedFileLocation,
    InputStickerSetThumb,
)


@handler.on_request(GetFile)
async def get_file(request: GetFile, user: User) -> TLFile:
    if not isinstance(request.location, SUPPORTED_LOCS):
        raise ErrorRpc(error_code=400, error_message="LOCATION_INVALID")
    if request.limit < 0 or request.limit > 1024 * 1024:
        raise ErrorRpc(error_code=400, error_message="LIMIT_INVALID")
    if request.offset < 0:
        raise ErrorRpc(error_code=400, error_message="OFFSET_INVALID")

    location = request.location
    ctx = request_ctx.get()

    if isinstance(location, InputPeerPhotoFileLocation):
        peer = await Peer.from_input_peer_raise(user, location.peer)
        if peer.type in (PeerType.SELF, PeerType.USER):
            q = {"userphotos__id": location.photo_id, "userphotos__user": peer.peer_user(user)}
        elif peer.type is PeerType.CHAT:
            q = {"chats__photo__id": location.photo_id, "chats__id": peer.chat_id}
        elif peer.type is PeerType.CHANNEL:
            q = {"channels__photo__id": location.photo_id, "channels__id": peer.channel_id}
        else:
            raise ErrorRpc(error_code=400, error_message="LOCATION_INVALID")
    elif isinstance(location, InputEncryptedFileLocation):
        if not File.check_access_hash(user.id, ctx.auth_id, location.id, location.access_hash):
            raise ErrorRpc(error_code=400, error_message="LOCATION_INVALID")
        q = {"id": location.id, "type": FileType.ENCRYPTED}
    elif isinstance(location, InputStickerSetThumb):
        set_q = Stickerset.from_input_q(location.stickerset, prefix="stickersetthumbs__set")
        if set_q is None:
            raise ErrorRpc(error_code=400, error_message="LOCATION_INVALID")
        q = Q(stickersetthumbs__id=location.thumb_version) | set_q
    else:
        valid, const = File.is_file_ref_valid(location.file_reference, user.id, location.id)
        if not valid:
            raise ErrorRpc(error_code=400, error_message="FILE_REFERENCE_EXPIRED")

        if const:
            q = {
                "id": location.id, "type__not": FileType.ENCRYPTED, "constant_access_hash": location.access_hash,
                "constant_file_ref": UUID(bytes=location.file_reference[12:]),
            }
        else:
            if not File.check_access_hash(user.id, ctx.auth_id, location.id, location.access_hash):
                raise ErrorRpc(error_code=400, error_message="LOCATION_INVALID")
            q = {"id": location.id, "type__not": FileType.ENCRYPTED}

    if isinstance(location, InputStickerSetThumb):
        file = await File.get_or_none(q)
        if file is None:
            raise ErrorRpc(error_code=400, error_message="LOCATION_INVALID")
    else:
        file = await File.get_or_none(**q)

    if file is None:
        raise ErrorRpc(error_code=400, error_message="FILE_REFERENCE_EXPIRED")

    if request.offset >= file.size:
        return TLFile(type_=FilePartial(), mtime=int(time()), bytes_=b"")

    document_thumb = isinstance(location, InputDocumentFileLocation) and location.thumb_size

    storage = request_ctx.get().storage
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

    data = await component.get_part(file.physical_id, request.offset, request.limit, suffix)
    data = data or b""

    if isinstance(location, (InputPhotoFileLocation, InputPeerPhotoFileLocation, InputStickerSetThumb)) \
            or document_thumb:
        file_type = FileJpeg()
    elif len(data) != file.size:
        file_type = FilePartial()
    else:
        file_type = MIME_TO_TL.get(file.mime_type, FileUnknown())

    return TLFile(type_=file_type, mtime=int(time()), bytes_=data)
