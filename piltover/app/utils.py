from piltover.app import files_dir
from piltover.db.enums import FileType
from piltover.db.models import User, UploadingFile, UploadingFilePart, File
from piltover.exceptions import ErrorRpc
from piltover.tl_new import InputFile


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
