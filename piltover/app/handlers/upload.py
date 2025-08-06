from time import time
from uuid import UUID

import aiofiles

from piltover.app import files_dir
from piltover.app.utils.utils import PHOTOSIZE_TO_INT, MIME_TO_TL
from piltover.db.enums import PeerType, FileType
from piltover.db.models import User, UploadingFile, UploadingFilePart, FileAccess, File, Peer
from piltover.exceptions import ErrorRpc
from piltover.tl import InputDocumentFileLocation, InputPhotoFileLocation, InputPeerPhotoFileLocation, \
    InputEncryptedFileLocation
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

    file, _ = await UploadingFile.get_or_create(user=user, file_id=request.file_id, defaults=defaults)
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
    if (size % 1024 != 0 or 524288 % size != 0) and last_part is not None and last_part.part_id >= request.file_part:
        raise ErrorRpc(error_code=400, error_message="FILE_PART_SIZE_INVALID")
    if size > 524288:
        raise ErrorRpc(error_code=400, error_message="FILE_PART_TOO_BIG")
    if size == 0:
        raise ErrorRpc(error_code=400, error_message="FILE_PART_EMPTY")

    part = await UploadingFilePart.create(file=file, part_id=request.file_part, size=size)

    # TODO: upload to s3 or something similar
    async with aiofiles.open(files_dir / "parts" / f"{part.physical_id}_{request.file_part}", "wb") as f:
        await f.write(request.bytes_)

    return True


SUPPORTED_LOCS = (
    InputDocumentFileLocation, InputPhotoFileLocation, InputPeerPhotoFileLocation, InputEncryptedFileLocation,
)


async def read_file_content(file: File, offset: int, limit: int, name: str | None = None) -> bytes:
    # TODO: download from s3 or something similar

    name = name or str(file.physical_id)
    async with aiofiles.open(files_dir / name, "rb") as f:
        await f.seek(offset)
        return await f.read(limit)


@handler.on_request(GetFile)
async def get_file(request: GetFile, user: User) -> TLFile:
    # noinspection PyPep8
    if not isinstance(request.location, SUPPORTED_LOCS):
        raise ErrorRpc(error_code=400, error_message="LOCATION_INVALID")
    if request.limit < 0 or request.limit > 1024 * 1024:
        raise ErrorRpc(error_code=400, error_message="LIMIT_INVALID")
    if request.offset < 0:
        raise ErrorRpc(error_code=400, error_message="OFFSET_INVALID")

    location = request.location
    ref_const = False

    if isinstance(location, InputPeerPhotoFileLocation):
        peer = await Peer.from_input_peer_raise(user, location.peer)
        if peer.type in (PeerType.SELF, PeerType.USER):
            q = {"file__userphotos__id": location.photo_id, "file__userphotos__user": peer.peer_user(user)}
        elif peer.type is PeerType.CHAT:
            q = {"file__chats__photo__id": location.photo_id, "file__chats__id": peer.chat_id}
        elif peer.type is PeerType.CHANNEL:
            q = {"file__channels__photo__id": location.photo_id, "file__channels__id": peer.channel_id}
        else:
            raise ErrorRpc(error_code=400, error_message="LOCATION_INVALID")
    elif isinstance(location, InputEncryptedFileLocation):
        q = {"file__id": location.id, "file__type": FileType.ENCRYPTED, "access_hash": location.access_hash}
    else:
        valid, const = FileAccess.is_file_ref_valid(location.file_reference, user.id, location.id)
        if not valid:
            raise ErrorRpc(error_code=400, error_message="FILE_REFERENCE_EXPIRED")

        if const:
            ref_const = True
            q = {
                "id": location.id, "type__not": FileType.ENCRYPTED, "constant_access_hash": location.access_hash,
                "constant_file_ref": UUID(bytes=location.file_reference[12:]),
            }
        else:
            q = {"file__id": location.id, "file__type__not": FileType.ENCRYPTED, "access_hash": location.access_hash}

    if ref_const:
        file = await File.get_or_none(**q)
    else:
        access = await FileAccess.get_or_none(user=user, **q).select_related("file")
        if not isinstance(location, InputPeerPhotoFileLocation) and access is None:
            raise ErrorRpc(error_code=400, error_message="FILE_REFERENCE_EXPIRED")
        elif isinstance(location, InputPeerPhotoFileLocation) and access is None:  # ?
            file = await File.get_or_none(userphotos__id=location.photo_id)
        else:
            file = access.file

    if file is None:
        raise ErrorRpc(error_code=400, error_message="FILE_REFERENCE_EXPIRED")

    if request.offset >= file.size:
        return TLFile(type_=FilePartial(), mtime=int(time()), bytes_=b"")

    f_name = str(file.physical_id)
    if isinstance(location, (InputPhotoFileLocation, InputPeerPhotoFileLocation)):
        if not file.photo_sizes:
            raise ErrorRpc(error_code=400, error_message="LOCATION_INVALID")  # not a photo
        if isinstance(location, InputPhotoFileLocation):
            size = PHOTOSIZE_TO_INT[location.thumb_size]
        else:
            size = 640 if location.big else 160
        available = [size["w"] for size in file.photo_sizes]
        if size not in available:
            size = min(available, key=lambda x: abs(x - size))
        f_name += f"_{size}"

    data = await read_file_content(file, request.offset, request.limit, f_name)

    if isinstance(location, (InputPhotoFileLocation, InputPeerPhotoFileLocation)):
        file_type = FileJpeg()
    elif len(data) != file.size:
        file_type = FilePartial()
    else:
        file_type = MIME_TO_TL.get(file.mime_type, FileUnknown())

    return TLFile(type_=file_type, mtime=int(time()), bytes_=data)
