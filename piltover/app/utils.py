from asyncio import get_event_loop, gather
from concurrent.futures import ThreadPoolExecutor

from PIL.Image import Image, open as img_open

from piltover.app import files_dir
from piltover.db.enums import FileType
from piltover.db.models import User, UploadingFile, UploadingFilePart, File
from piltover.exceptions import ErrorRpc
from piltover.tl_new import InputFile
from piltover.tl_new.types.storage import FileJpeg, FileGif, FilePng, FilePdf, FileMp3, FileMov, FileMp4, FileWebp


async def upload_file(user: User, input_file: InputFile, mime_type: str, attributes: list) -> File:
    uploaded_file = await UploadingFile.get_or_none(user=user, file_id=input_file.id)
    parts = await UploadingFilePart.filter(file=uploaded_file).order_by("part_id")
    if (uploaded_file.total_parts > 0 and uploaded_file.total_parts != len(parts)) or not parts:
        raise ErrorRpc(error_code=400, error_message="FILE_PARTS_INVALID")

    size = parts[0].size
    for idx, part in enumerate(parts):
        if part == parts[0]:
            continue
        if part.part_id - 1 != parts[idx - 1]:
            raise ErrorRpc(error_code=400, error_message=f"FILE_PART_{part.part_id - 1}_MISSING")
        size += part.size

    file = await File.create(
        mime_type=mime_type,
        size=size,
        type=FileType.DOCUMENT,
        attributes=File.attributes_from_tl(attributes)
    )

    with open(files_dir / f"{file.physical_id}", "wb") as f_out:
        for part in parts:
            with open(files_dir / "parts" / f"{part.physical_id}_{part.part_id}", "rb") as f_part:
                f_out.write(f_part.read())

    return file


MIME_TO_TL = {
    "image/jpeg": FileJpeg(),
    "image/gif": FileGif(),
    "image/png": FilePng(),
    "application/pdf": FilePdf(),
    "audio/mpeg": FileMp3(),
    "video/quicktime": FileMov(),
    "video/mp4": FileMp4(),
    "image/webp": FileWebp(),
}

PHOTOSIZE_TO_INT = {
    "a": 160,
    "b": 320,
    "c": 640,
    "d": 1280,

    "s": 100,
    "m": 320,
    "x": 800,
    "y": 1280,
    "w": 2560,
}


def resize_image_internal(file_id: str, img: Image, size: int) -> int:
    with open(files_dir / f"{file_id}_{size}", "wb") as f_out:
        img.resize((size, size)).save(f_out, format="PNG")
        return f_out.tell()


async def resize_photo(file_id: str) -> list[dict[str, int | str]]:
    types = ["a", "b", "c"]
    sizes = [160, 320, 640]

    img = img_open(files_dir / f"{file_id}")
    img.load()
    with ThreadPoolExecutor() as pool:
        tasks = [
            get_event_loop().run_in_executor(pool, lambda: resize_image_internal(file_id, img, size))
            for size in sizes
        ]
        res = await gather(*tasks)

    return [
        {"type_": types[idx], "w": sizes[idx], "h": sizes[idx], "size": file_size}
        for idx, file_size in enumerate(res)
    ]
