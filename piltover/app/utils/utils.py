import asyncio
import ctypes
import re
from asyncio import get_event_loop, gather
from concurrent.futures.thread import ThreadPoolExecutor
from hashlib import md5
from io import BytesIO
from typing import Iterable, Literal

from PIL.Image import Image, open as img_open
from loguru import logger

from piltover.app import files_dir
from piltover.db.models import UserPassword, SrpSession, AuthKey, TempAuthKey
from piltover.exceptions import ErrorRpc
from piltover.tl import InputCheckPasswordEmpty, InputCheckPasswordSRP, MessageEntityHashtag, MessageEntityMention, \
    MessageEntityUnknown, MessageEntityBotCommand, MessageEntityUrl, MessageEntityEmail, MessageEntityBold, \
    MessageEntityItalic, MessageEntityCode, MessageEntityPre, MessageEntityTextUrl, MessageEntityMentionName, \
    MessageEntityPhone, MessageEntityCashtag, MessageEntityUnderline, MessageEntityStrike, MessageEntitySpoiler, \
    MessageEntityBankCard, MessageEntityBlockquote, Long
from piltover.tl.types.storage import FileJpeg, FileGif, FilePng, FilePdf, FileMp3, FileMov, FileMp4, FileWebp
from piltover.utils import gen_safe_prime
from piltover.utils.srp import sha256d, itob, btoi
from piltover.utils.utils import xor

USERNAME_MENTION_REGEX = re.compile(r'@[a-z0-9_]{5,32}')
USERNAME_REGEX = re.compile(r'^[a-z0-9_]{5,32}$')
USERNAME_REGEX_NO_LEN = re.compile(r'[a-z0-9_]{1,32}')

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

image_executor = ThreadPoolExecutor(thread_name_prefix="ImageResizeWorker")


def resize_image_internal(file_id: str, width: int) -> tuple[int, int]:
    img = img_open(files_dir / f"{file_id}")
    img.load()

    original_width, height = img.size
    factor = width / original_width
    height *= factor
    height = int(height)

    with open(files_dir / f"{file_id}_{width}", "wb") as f_out:
        img.resize((width, height)).save(f_out, format="JPEG")
        return f_out.tell(), height


async def resize_photo(file_id: str, sizes: str = "abc") -> list[dict[str, int | str]]:
    tasks = [
        get_event_loop().run_in_executor(image_executor, resize_image_internal, file_id, PHOTOSIZE_TO_INT[size])
        for size in sizes
    ]
    res = await gather(*tasks)

    return [
        {"type_": sizes[idx], "w": PHOTOSIZE_TO_INT[sizes[idx]], "h": height, "size": file_size}
        for idx, (file_size, height) in enumerate(res)
    ]


def _get_image_dims(file_id: str) -> tuple[int, int] | None:
    try:
        img = img_open(files_dir / f"{file_id}")
        img.load()
    except Exception as e:
        logger.opt(exception=e).error("Failed to load image!")
        return None

    return img.size


async def get_image_dims(file_id: str) -> tuple[int, int] | None:
    return await get_event_loop().run_in_executor(image_executor, _get_image_dims, file_id)


async def generate_stripped(file_id: str, size: int = 8) -> bytes:
    def _gen(im: Image) -> bytes:
        img_file = BytesIO()

        im = im.convert("RGB").resize((size, size))
        im.save(img_file, "JPEG", qtables=TELEGRAM_QUANTIZATION_TABLES)

        img_file.seek(0)
        header_offset = 623  # 619 + 4, 619 is header size, 4 is width and height

        return img_file.read()[header_offset:]

    img = img_open(files_dir / f"{file_id}")

    return await get_event_loop().run_in_executor(image_executor, _gen, img)


async def check_password_internal(password: UserPassword, check: InputCheckPasswordEmpty | InputCheckPasswordSRP):
    if password.password is not None and isinstance(check, InputCheckPasswordEmpty):
        raise ErrorRpc(error_code=400, error_message="PASSWORD_HASH_INVALID")

    if password.password is None:
        return

    if (sess := await SrpSession.get_current(password)).id != check.srp_id:
        raise ErrorRpc(error_code=400, error_message="SRP_ID_INVALID")

    p, g = gen_safe_prime()

    u = sha256d(check.A + sess.pub_B())
    s_b = pow(btoi(check.A) * pow(btoi(password.password), btoi(u), p), btoi(sess.priv_b), p)
    k_b = sha256d(itob(s_b))

    M2 = sha256d(
        xor(sha256d(itob(p)), sha256d(itob(g)))
        + sha256d(password.salt1)
        + sha256d(password.salt2)
        + check.A
        + sess.pub_B()
        + k_b
    )

    if check.M1 != M2:
        raise ErrorRpc(error_code=400, error_message="PASSWORD_HASH_INVALID")


async def get_perm_key(unk_key_id: int) -> AuthKey | None:
    key = await AuthKey.get_or_temp(unk_key_id)
    return key.perm_key if isinstance(key, TempAuthKey) else key


MessageEntity = MessageEntityUnknown | MessageEntityMention | MessageEntityHashtag | MessageEntityBotCommand \
                | MessageEntityUrl | MessageEntityEmail | MessageEntityBold | MessageEntityItalic | MessageEntityCode \
                | MessageEntityPre | MessageEntityTextUrl | MessageEntityMentionName | MessageEntityPhone \
                | MessageEntityCashtag | MessageEntityUnderline | MessageEntityStrike | MessageEntityBankCard \
                | MessageEntitySpoiler | MessageEntityBlockquote

VALID_ENTITIES = (
    MessageEntityBold, MessageEntityItalic, MessageEntityCode, MessageEntityPre, MessageEntityTextUrl,
    MessageEntityUnderline, MessageEntityStrike, MessageEntityBankCard, MessageEntitySpoiler, MessageEntityBlockquote
)


async def validate_message_entities(text: str, entities: list[MessageEntity]) -> list[dict] | None:
    if not entities:
        return None
    # TODO: check what limit telegram has
    if len(entities) > 1024:
        raise ErrorRpc(error_code=400, error_message="ENTITIES_TOO_LONG")

    result = []
    for idx, entity in enumerate(entities):
        if (idx % 64) == 0:
            await asyncio.sleep(0)

        if entity.offset < 0 or entity.offset > len(text) or (entity.offset + entity.length) > len(text):
            raise ErrorRpc(error_code=400, error_message="ENTITY_BOUNDS_INVALID")
        if isinstance(entity, MessageEntityMention):
            if text[entity.offset] != "@":
                raise ErrorRpc(error_code=400, error_message="ENTITY_BOUNDS_INVALID")
            if not USERNAME_REGEX.match(text[entity.offset+1:entity.offset+entity.length]):
                raise ErrorRpc(error_code=400, error_message="ENTITY_MENTION_USER_INVALID")
        elif isinstance(entity, MessageEntityHashtag):
            if text[entity.offset] != "#":
                raise ErrorRpc(error_code=400, error_message="ENTITY_BOUNDS_INVALID")
        elif isinstance(entity, MessageEntityBotCommand):
            if text[entity.offset] != "/":
                raise ErrorRpc(error_code=400, error_message="ENTITY_BOUNDS_INVALID")
        elif isinstance(entity, MessageEntityUrl):
            if not text[entity.offset:].startswith("http"):
                raise ErrorRpc(error_code=400, error_message="ENTITY_BOUNDS_INVALID")
        elif isinstance(entity, MessageEntityEmail):
            email = text[entity.offset+1:entity.offset+entity.length]
            if "@" not in email:
                raise ErrorRpc(error_code=400, error_message="ENTITY_BOUNDS_INVALID")
        elif isinstance(entity, MessageEntityPhone):
            if text[entity.offset] != "+":
                raise ErrorRpc(error_code=400, error_message="ENTITY_BOUNDS_INVALID")
        elif isinstance(entity, MessageEntityCashtag):
            if text[entity.offset] != "$":
                raise ErrorRpc(error_code=400, error_message="ENTITY_BOUNDS_INVALID")
        elif not isinstance(entity, VALID_ENTITIES):
            continue

        result.append(entity.to_dict() | {"_": entity.tlid()})

    return result or None


async def process_message_entities(text: str | None, entities: list[MessageEntity]) -> list[dict] | None:
    if not text:
        return None

    entities = await validate_message_entities(text, entities)

    for mention in USERNAME_MENTION_REGEX.finditer(text):
        if entities is None:
            entities = []

        start, end = mention.span()
        length = end - start
        entities.append({
            "_": MessageEntityMention.tlid(),
            "offset": start,
            "length": length,
        })

    return entities


def validate_username(username: str) -> None:
    if len(username) not in range(5, 32) or not USERNAME_REGEX.match(username):
        raise ErrorRpc(error_code=400, error_message="USERNAME_INVALID")


def telegram_hash(ids: Iterable[int | str], bits: Literal[32, 64]) -> int:
    result_hash = 0
    for id_to_hash in ids:
        result_hash ^= result_hash >> 21
        result_hash ^= result_hash << 35
        result_hash ^= result_hash >> 4
        if isinstance(id_to_hash, int):
            result_hash += id_to_hash
        elif isinstance(id_to_hash, str):
            result_hash += Long.read_bytes(md5(id_to_hash.encode("utf8")).digest()[:8])

    result_hash &= ((2 << bits - 1) - 1)

    if bits == 32:
        return ctypes.c_int32(result_hash).value
    elif bits == 64:
        return ctypes.c_int64(result_hash).value
    else:
        raise RuntimeError("Unreachable")
