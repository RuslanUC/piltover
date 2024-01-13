from piltover.app import files_dir
from piltover.db.models import User, UploadingFile, UploadingFilePart
from piltover.exceptions import ErrorRpc
from piltover.high_level import MessageHandler, Client
from piltover.tl_new.functions.upload import SaveFilePart, SaveBigFilePart

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
