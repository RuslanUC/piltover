from time import time

from piltover.app import files_dir
from piltover.db.models import User, UploadingFile, UploadingFilePart, FileAccess
from piltover.exceptions import ErrorRpc
from piltover.high_level import MessageHandler, Client
from piltover.tl_new import InputDocumentFileLocation
from piltover.tl_new.functions.upload import SaveFilePart, SaveBigFilePart, GetFile
from piltover.tl_new.types.storage import FileUnknown, FilePartial, FileJpeg, FileWebp, FileMp4, FileMov, FileMp3, \
    FilePdf, FilePng, FileGif
from piltover.tl_new.types.upload import File as TLFile

handler = MessageHandler("upload")


# noinspection PyUnusedLocal
@handler.on_request(SaveFilePart, True)
@handler.on_request(SaveBigFilePart, True)
async def save_file_part(client: Client, request: SaveFilePart | SaveBigFilePart, user: User):
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
    if (size % 1024 != 0 or 524288 % size != 0) and last_part is not None and last_part.part_id >= request.file_part:
        raise ErrorRpc(error_code=400, error_message="FILE_PART_SIZE_INVALID")
    if await UploadingFilePart.filter(file=file, part_id=request.file_part).exists():
        raise ErrorRpc(error_code=400, error_message="FILE_PART_INVALID3")
    if size > 524288:
        raise ErrorRpc(error_code=400, error_message="FILE_PART_TOO_BIG")
    if size == 0:
        raise ErrorRpc(error_code=400, error_message="FILE_PART_EMPTY")

    part = await UploadingFilePart.create(file=file, part_id=request.file_part, size=size)

    with open(files_dir / "parts" / f"{part.physical_id}_{request.file_part}", "wb") as f:
        f.write(request.bytes_)

    return True


# noinspection PyUnusedLocal
@handler.on_request(GetFile, True)
async def get_file(client: Client, request: GetFile, user: User):
    if not isinstance(request.location, InputDocumentFileLocation):
        raise ErrorRpc(error_code=400, error_message="LOCATION_INVALID")
    if request.limit < 0 or request.limit > 1024 * 1024:
        raise ErrorRpc(error_code=400, error_message="LIMIT_INVALID")

    access = await FileAccess.get_or_none(file__id=request.location.id, user=user).select_related("file")
    if access is None or access.is_expired() or access.access_hash != request.location.access_hash:
        raise ErrorRpc(error_code=400, error_message="FILE_REFERENCE_EXPIRED")

    file = access.file
    if request.offset >= file.size:
        raise ErrorRpc(error_code=400, error_message="OFFSET_INVALID")

    with open(files_dir / f"{file.physical_id}", "rb") as f:
        f.seek(request.offset)
        data = f.read(request.limit)

    file_type = FileUnknown()
    if len(data) != file.size:
        file_type = FilePartial()
    elif file.mime_type == "image/jpeg":
        file_type = FileJpeg()
    elif file.mime_type == "image/gif":
        file_type = FileGif()
    elif file.mime_type == "image/png":
        file_type = FilePng()
    elif file.mime_type == "application/pdf":
        file_type = FilePdf()
    elif file.mime_type == "audio/mpeg":
        file_type = FileMp3()
    elif file.mime_type == "video/quicktime":
        file_type = FileMov()
    elif file.mime_type == "video/mp4":
        file_type = FileMp4()
    elif file.mime_type == "image/webp":
        file_type = FileWebp()

    return TLFile(type_=file_type, mtime=int(time()), bytes_=data)
