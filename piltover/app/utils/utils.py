from asyncio import get_event_loop, gather
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO

from PIL.Image import Image, open as img_open

from piltover.app import files_dir
from piltover.db.enums import FileType
from piltover.db.models import User, UploadingFile, UploadingFilePart, File, UserPassword, SrpSession
from piltover.exceptions import ErrorRpc
from piltover.tl_new import InputFile, InputCheckPasswordEmpty, InputCheckPasswordSRP
from piltover.tl_new.types.storage import FileJpeg, FileGif, FilePng, FilePdf, FileMp3, FileMov, FileMp4, FileWebp
from piltover.utils import gen_safe_prime
from piltover.utils.srp import sha256, itob, btoi, xor


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

TELEGRAM_QUANTIZATION_TABLES = {
    0: [
        40, 28, 25, 40, 60, 100, 128, 153,
        30, 30, 35, 48, 65, 145, 150, 138,
        35, 33, 40, 60, 100, 143, 173, 140,
        35, 43, 55, 73, 128, 218, 200, 155,
        45, 55, 93, 140, 170, 255, 255, 193,
        60, 88, 138, 160, 203, 255, 255, 230,
        123, 160, 195, 218, 255, 255, 255, 253,
        180, 230, 238, 245, 255, 250, 255, 248
    ],
    1: [
        43, 45, 60, 118, 248, 248, 248, 248,
        45, 53, 65, 165, 248, 248, 248, 248,
        60, 65, 140, 248, 248, 248, 248, 248,
        118, 165, 248, 248, 248, 248, 248, 248,
        248, 248, 248, 248, 248, 248, 248, 248,
        248, 248, 248, 248, 248, 248, 248, 248,
        248, 248, 248, 248, 248, 248, 248, 248,
        248, 248, 248, 248, 248, 248, 248, 248
    ]
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


async def generate_stripped(file_id: str, size: int = 8) -> bytes:
    def _gen(im: Image) -> bytes:
        img_file = BytesIO()

        im = im.convert("RGB").resize((size, size))
        im.save(img_file, 'JPEG', qtables=TELEGRAM_QUANTIZATION_TABLES)

        img_file.seek(0)
        header_offset = 623  # 619 + 4, 619 is header size, 4 is width and height

        return img_file.read()[header_offset:]

    img = img_open(files_dir / f"{file_id}")
    with ThreadPoolExecutor() as pool:
        res = await gather(get_event_loop().run_in_executor(pool, lambda: _gen(img)))

    return res[0]


async def check_password_internal(password: UserPassword, check: InputCheckPasswordEmpty | InputCheckPasswordSRP):
    if password.password is not None and isinstance(check, InputCheckPasswordEmpty):
        raise ErrorRpc(error_code=400, error_message="PASSWORD_HASH_INVALID")

    if password.password is None:
        return

    if (sess := await SrpSession.get_current(password)).id != check.srp_id:
        raise ErrorRpc(error_code=400, error_message="SRP_ID_INVALID")

    p, g = gen_safe_prime()

    u = sha256(check.A + sess.pub_B())
    s_b = pow(btoi(check.A) * pow(btoi(password.password), btoi(u), p), btoi(sess.priv_b), p)
    k_b = sha256(itob(s_b))

    M2 = sha256(
        xor(sha256(itob(p)), sha256(itob(g)))
        + sha256(password.salt1)
        + sha256(password.salt2)
        + check.A
        + sess.pub_B()
        + k_b
    )

    if check.M1 != M2:
        raise ErrorRpc(error_code=400, error_message="PASSWORD_HASH_INVALID")
