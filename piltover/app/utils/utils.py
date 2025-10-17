import asyncio
import ctypes
import os
import re
from asyncio import get_event_loop, gather, sleep
from concurrent.futures.thread import ThreadPoolExecutor
from contextlib import ExitStack
from hashlib import md5
from io import BytesIO
from typing import Iterable, Literal
from uuid import UUID

import av
from PIL.Image import Image, open as img_open
from loguru import logger
from tortoise.expressions import Q

from piltover.db.models import UserPassword, SrpSession, User, Peer
from piltover.exceptions import ErrorRpc
from piltover.storage.base import BaseStorage, StorageType
from piltover.tl import InputCheckPasswordEmpty, MessageEntityHashtag, MessageEntityMention, \
    MessageEntityBotCommand, MessageEntityUrl, MessageEntityEmail, MessageEntityBold, \
    MessageEntityItalic, MessageEntityCode, MessageEntityPre, MessageEntityTextUrl, MessageEntityMentionName, \
    MessageEntityPhone, MessageEntityCashtag, MessageEntityUnderline, MessageEntityStrike, MessageEntitySpoiler, \
    MessageEntityBankCard, MessageEntityBlockquote, Long, InputMessageEntityMentionName, InputUserSelf, InputUser, \
    InputUserFromMessage
from piltover.tl.base import InputCheckPasswordSRP as InputCheckPasswordSRPBase, InputUser as InputUserBase, \
    MessageEntity as MessageEntityBase
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
video_executor = ThreadPoolExecutor(thread_name_prefix="VideoMetadataWorker")


def _resize_image_internal(location: str, width: int) -> tuple[BytesIO, int]:
    img = img_open(location)
    img.load()

    original_width, height = img.size
    factor = width / original_width
    height *= factor
    height = int(height)

    out = BytesIO()
    img.resize((width, height)).save(out, format="JPEG")
    return out, height


async def resize_photo(
        storage: BaseStorage, file_id: UUID, sizes: str = "abc", suffix: str | None = None, is_document: bool = False,
) -> list[dict[str, int | str]]:
    if is_document:
        location = await storage.documents.get_location(file_id, suffix)
    else:
        location = await storage.photos.get_location(file_id, suffix)

    tasks = [
        get_event_loop().run_in_executor(
            image_executor, _resize_image_internal,
            location, PHOTOSIZE_TO_INT[size],
        )
        for size in sizes
    ]
    res: list[tuple[BytesIO, int]] = await gather(*tasks)

    result = []

    for idx, (resized, height) in enumerate(res):
        width = PHOTOSIZE_TO_INT[sizes[idx]]

        await sleep(0)

        resized.seek(0, os.SEEK_END)
        file_size = resized.tell()
        resized.seek(0)

        await storage.save_part(file_id, 0, resized.getbuffer(), True, str(width))
        await storage.finalize_upload_as(file_id, StorageType.PHOTO, 0, str(width))

        result.append({
            "type_": sizes[idx],
            "w": width,
            "h": height,
            "size": file_size,
        })

    return result


def _get_image_dims(location: str) -> tuple[int, int] | None:
    try:
        img = img_open(location)
        img.load()
    except Exception as e:
        logger.opt(exception=e).error("Failed to load image!")
        return None

    return img.size


async def get_image_dims(storage: BaseStorage, file_id: UUID) -> tuple[int, int] | None:
    return await get_event_loop().run_in_executor(
        image_executor, _get_image_dims,
        await storage.documents.get_location(file_id),
    )


def _generate_stripped(location: str, size: int) -> bytes:
    img = img_open(location)
    img_file = BytesIO()

    img = img.convert("RGB").resize((size, size))
    img.save(img_file, "JPEG", qtables=TELEGRAM_QUANTIZATION_TABLES)

    header_offset = 623  # 619 + 4, 619 is header size, 4 is width and height
    img_file.seek(header_offset)

    return img_file.read()


async def generate_stripped(
        storage: BaseStorage, file_id: UUID, size: int = 8, suffix: str | None = None, is_document: bool = False,
) -> bytes:
    if is_document:
        location = await storage.documents.get_location(file_id, suffix)
    else:
        location = await storage.photos.get_location(file_id, suffix)

    return await get_event_loop().run_in_executor(
        image_executor, _generate_stripped,
        location, size,
    )


def _extract_video_metadata(location: str) -> tuple[int, bool, bool, Image | None]:
    exit_stack = ExitStack()
    # TODO: might be url (e.g. s3) in the future
    file = exit_stack.enter_context(open(location, "rb"))
    container = exit_stack.enter_context(av.open(file, options={"probesize": "16k", "analyzeduration": "200000"}))

    has_audio = any(s.type == "audio" for s in container.streams)
    has_video = any(s.type == "video" for s in container.streams)
    duration = container.duration // av.time_base if container.duration else None
    for stream in container.streams.video:
        for packet in container.demux(stream):
            for frame in packet.decode():
                return duration, has_video, has_audio, frame.to_image()

    return duration, has_video, has_audio, None


async def extract_video_metadata(location: str) -> tuple[int, bool, bool, Image | None]:
    return await get_event_loop().run_in_executor(video_executor, _extract_video_metadata, location)


async def check_password_internal(password: UserPassword, check: InputCheckPasswordSRPBase) -> None:
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


VALID_ENTITIES = (
    MessageEntityBold, MessageEntityItalic, MessageEntityCode, MessageEntityPre, MessageEntityTextUrl,
    MessageEntityUnderline, MessageEntityStrike, MessageEntityBankCard, MessageEntitySpoiler, MessageEntityBlockquote
)


async def validate_message_entities(text: str, entities: list[MessageEntityBase], user: User) -> list[dict] | None:
    if not entities:
        return None
    if len(entities) > 1024:
        raise ErrorRpc(error_code=400, error_message="ENTITIES_TOO_LONG")

    fetch_users: list[tuple[InputUserBase, int]] = []

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
        elif isinstance(entity, InputMessageEntityMentionName):
            fetch_users.append((entity.user_id, len(result)))
            entity = MessageEntityMentionName(offset=entity.offset, length=entity.length, user_id=0)
        elif not isinstance(entity, VALID_ENTITIES):
            continue

        result.append(entity.to_dict() | {"_": entity.tlid()})

    if fetch_users:
        got_users = {user.id}
        users_q = Q()
        for input_user, _ in fetch_users:
            if isinstance(input_user, InputUser):
                users_q |= Q(user__id=input_user.user_id, access_hash=input_user.access_hash)
            # TODO: InputUserFromMessage

        got_users.update(await Peer.filter(users_q, owner=user).values_list("user__id", flat=True))

        for input_user, idx in reversed(fetch_users):
            # entity = cast(MessageEntityMentionName, result[idx])
            entity = result[idx]
            if isinstance(input_user, InputUserSelf):
                entity["user_id"] = user.id
            elif isinstance(input_user, (InputUser, InputUserFromMessage)):
                if input_user.user_id in got_users:
                    entity["user_id"] = input_user.user_id
                else:
                    del result[idx]

    return result or None


async def process_message_entities(
        text: str | None, entities: list[MessageEntityBase], user: User,
) -> list[dict] | None:
    if not text:
        return None

    entities = await validate_message_entities(text, entities, user)

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
