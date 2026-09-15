import hashlib
import math
import os
from collections.abc import Iterable, AsyncGenerator

import pytest
from pyrogram.errors import FilePartSizeChanged, FilePartInvalid
from pyrogram.raw.functions.messages import UploadMedia
from pyrogram.raw.functions.upload import SaveBigFilePart, GetFile, SaveFilePart
from pyrogram.raw.types import InputPeerSelf, InputMediaUploadedDocument, InputFileBig, MessageMediaDocument, Document, \
    InputDocumentFileLocation, InputFile
from pyrogram.raw.types.upload import File

from piltover.config import APP_CONFIG
from tests.client import TestClient
from tests.conftest import ClientFactory


@pytest.mark.parametrize(
    ("total_parts", "part_sizes_kb", "parts_order", "check_download_parts"),
    [
        (4, (256, 256, 256, 128), (0, 1, 2, 3), (1,)),
        (4, (256, 256, 256, 128), (0, 2, 1, 3), (1,)),
        (4, (256, 256, 256, 128), (1, 0, 2, 3), (1,)),
        (4, (256, 256, 256, 128), (3, 0, 2, 1), (1,)),
        (4, (256, 256, 256, 128), (0, 1, 2, -1, 3), (1,)),
    ],
    ids=(
        "regular in-order upload",
        "out-of-order upload - first is first",
        "out-of-order upload - first is not first",
        "out-of-order upload - last is first",
        "reupload one part reversed",
    ),
)
@pytest.mark.asyncio
async def test_save_big_file(
        client_with_auth: ClientFactory, part_sizes_kb: tuple[int, ...], parts_order: tuple[int, ...], total_parts: int,
        check_download_parts: tuple[int, ...],
) -> None:
    client = await client_with_auth(run=True)

    actual_parts = [
        os.urandom(1024 * part_size_kb)
        for part_size_kb in part_sizes_kb
    ]

    part_offsets = [0]
    for part_id in range(1, len(actual_parts)):
        part_offsets.append(part_offsets[part_id - 1] + len(actual_parts[part_id - 1]))

    parts_to_upload: list[tuple[int, bytes]] = []
    reversed_parts = [False] * len(actual_parts)
    for part_id in parts_order:
        if part_id >= 0:
            part_bytes = actual_parts[part_id]
            reversed_parts[part_id] = False
        else:
            part_id = -part_id - 1
            part_bytes = actual_parts[part_id][::-1]
            reversed_parts[part_id] = True
        parts_to_upload.append((part_id, part_bytes))

    file_id = client.rnd_id()
    for idx, part in parts_to_upload:
        assert await client.invoke(SaveBigFilePart(
            file_id=file_id,
            file_part=idx,
            file_total_parts=total_parts,
            bytes=part,
        ))

    result = await client.invoke(UploadMedia(
        peer=InputPeerSelf(),
        media=InputMediaUploadedDocument(
            file=InputFileBig(
                id=file_id,
                parts=2,
                name="idk.bin",
            ),
            mime_type="application/octet-stream",
            attributes=[],
        ),
    ))

    assert isinstance(result, MessageMediaDocument)
    doc = result.document
    assert isinstance(doc, Document)

    for check_part in check_download_parts:
        check_bytes = actual_parts[check_part]
        if reversed_parts[check_part]:
            check_bytes = check_bytes[::-1]

        file_result = await client.invoke(GetFile(
            location=InputDocumentFileLocation(
                id=doc.id,
                access_hash=doc.access_hash,
                file_reference=doc.file_reference,
                thumb_size="",
            ),
            offset=part_offsets[check_part],
            limit=len(check_bytes),
            precise=False,
        ))
        assert isinstance(file_result, File)
        assert file_result.bytes == check_bytes


@pytest.mark.asyncio
async def test_save_big_file_part_size_changed(client_with_auth: ClientFactory) -> None:
    client = await client_with_auth(run=True)
    file_id = client.rnd_id()

    part0 = os.urandom(256 * 1024)
    part1 = os.urandom(128 * 1024)

    assert await client.invoke(SaveBigFilePart(file_id=file_id, file_part=0, file_total_parts=3, bytes=part0))
    with pytest.raises(FilePartSizeChanged):
        assert await client.invoke(SaveBigFilePart(file_id=file_id, file_part=1, file_total_parts=3, bytes=part1))


@pytest.mark.asyncio
async def test_save_big_file_first_part_size_changed(client_with_auth: ClientFactory) -> None:
    client = await client_with_auth(run=True)
    file_id = client.rnd_id()

    part0 = os.urandom(256 * 1024)
    part1 = os.urandom(128 * 1024)

    assert await client.invoke(SaveBigFilePart(file_id=file_id, file_part=1, file_total_parts=3, bytes=part1))
    with pytest.raises(FilePartSizeChanged):
        assert await client.invoke(SaveBigFilePart(file_id=file_id, file_part=0, file_total_parts=3, bytes=part0))


@pytest.mark.asyncio
async def test_save_big_file_extra_part(client_with_auth: ClientFactory) -> None:
    client = await client_with_auth(run=True)
    file_id = client.rnd_id()

    part0 = os.urandom(256 * 1024)
    part1 = os.urandom(128 * 1024)
    part2 = os.urandom(128 * 1024)

    assert await client.invoke(SaveBigFilePart(file_id=file_id, file_part=0, file_total_parts=2, bytes=part0))
    assert await client.invoke(SaveBigFilePart(file_id=file_id, file_part=1, file_total_parts=2, bytes=part1))
    with pytest.raises(FilePartInvalid):
        assert await client.invoke(SaveBigFilePart(file_id=file_id, file_part=2, file_total_parts=3, bytes=part2))


@pytest.mark.asyncio
async def test_save_big_file_part_size_changed_last_part(client_with_auth: ClientFactory) -> None:
    client = await client_with_auth(run=True)
    file_id = client.rnd_id()

    part0 = os.urandom(256 * 1024)
    part1 = os.urandom(256 * 1024)
    part2 = os.urandom(256 * 1024)
    part2_new = os.urandom(128 * 1024)

    assert await client.invoke(SaveBigFilePart(file_id=file_id, file_part=0, file_total_parts=3, bytes=part0))
    assert await client.invoke(SaveBigFilePart(file_id=file_id, file_part=1, file_total_parts=3, bytes=part1))
    assert await client.invoke(SaveBigFilePart(file_id=file_id, file_part=2, file_total_parts=3, bytes=part2))
    assert await client.invoke(SaveBigFilePart(file_id=file_id, file_part=2, file_total_parts=3, bytes=part2_new))

    result = await client.invoke(UploadMedia(
        peer=InputPeerSelf(),
        media=InputMediaUploadedDocument(
            file=InputFileBig(id=file_id, parts=2, name="idk.bin"),
            mime_type="application/octet-stream",
            attributes=[],
        ),
    ))

    assert isinstance(result, MessageMediaDocument)
    doc = result.document
    assert isinstance(doc, Document)

    file_result = await client.invoke(GetFile(
        location=InputDocumentFileLocation(
            id=doc.id,
            access_hash=doc.access_hash,
            file_reference=doc.file_reference,
            thumb_size="",
        ),
        offset=512 * 1024,
        limit=256 * 1024,
        precise=False,
    ))
    assert isinstance(file_result, File)
    assert file_result.bytes == part2_new


async def _stream_download(client: TestClient, document: Document) -> AsyncGenerator[bytes]:
    one_mb_parts = math.ceil(document.size / 1024 / 1024)

    for part_num in range(one_mb_parts):
        length = 1024 * 1024
        offset = length * part_num

        file_result = await client.invoke(GetFile(
            location=InputDocumentFileLocation(
                id=document.id,
                access_hash=document.access_hash,
                file_reference=document.file_reference,
                thumb_size="",
            ),
            offset=offset,
            limit=length,
            precise=False,
        ))

        assert isinstance(file_result, File)
        yield file_result.bytes


@pytest.mark.parametrize(
    ("part_sizes", "chunk_size"),
    [
        ((256, 256, 256, 128), 1024,),
        ((256, 127, 128, 512), 1024,),
        ((256, 127, 128, 512), 1023,),
        ((512,) * 32, 1024,),
    ],
    ids=(
        "regular",
        "different sizes",
        "different sizes, not 1kb-divisible",
        "max size file",
    )
)
@pytest.mark.asyncio
async def test_save_file_part(client_with_auth: ClientFactory, part_sizes: tuple[int, ...], chunk_size: int) -> None:
    APP_CONFIG.upload_small_file_max_size_kb = 1024 * 16

    client = await client_with_auth(run=True)
    file_id = client.rnd_id()

    parts = [
        os.urandom(part_size * chunk_size)
        for part_size in part_sizes
    ]

    for part_id, part_bytes in enumerate(parts):
        assert await client.invoke(SaveFilePart(file_id=file_id, file_part=part_id, bytes=part_bytes))

    file_content = b"".join(parts)
    checksum = hashlib.md5(file_content).hexdigest()

    result = await client.invoke(UploadMedia(
        peer=InputPeerSelf(),
        media=InputMediaUploadedDocument(
            file=InputFile(id=file_id, parts=len(parts), name="idk.bin", md5_checksum=checksum),
            mime_type="application/octet-stream",
            attributes=[],
        ),
    ))

    assert isinstance(result, MessageMediaDocument)
    doc = result.document
    assert isinstance(doc, Document)

    part_num = 0
    length = 1024 * 1024
    async for chunk in _stream_download(client, doc):
        offset = length * part_num
        part_num += 1
        assert chunk == file_content[offset:offset + length]


@pytest.mark.asyncio
async def test_save_file_part_max_size_exceeded(client_with_auth: ClientFactory) -> None:
    client = await client_with_auth(run=True)
    file_id = client.rnd_id()

    part = os.urandom(512 * 1024)

    parts_num = APP_CONFIG.upload_small_file_max_size_kb * 2 // 1024

    for part_id in range(parts_num):
        assert await client.invoke(SaveFilePart(file_id=file_id, file_part=part_id, bytes=part))

    with pytest.raises(FilePartInvalid):
        await client.invoke(SaveFilePart(file_id=file_id, file_part=parts_num, bytes=part))


@pytest.mark.asyncio
async def test_save_file_part_reupload_smaller_part_near_limit(client_with_auth: ClientFactory) -> None:
    client = await client_with_auth(run=True)
    file_id = client.rnd_id()

    part = os.urandom(512 * 1024)
    part_small = os.urandom(256 * 1024)

    parts_num = APP_CONFIG.upload_small_file_max_size_kb * 2 // 1024

    for part_id in range(parts_num):
        assert await client.invoke(SaveFilePart(file_id=file_id, file_part=part_id, bytes=part))

    await client.invoke(SaveFilePart(file_id=file_id, file_part=parts_num - 1, bytes=part_small))
    await client.invoke(SaveFilePart(file_id=file_id, file_part=parts_num, bytes=part_small))

    file_content = part * (parts_num - 1) + part_small * 2
    checksum = hashlib.md5(file_content).hexdigest()

    result = await client.invoke(UploadMedia(
        peer=InputPeerSelf(),
        media=InputMediaUploadedDocument(
            file=InputFile(id=file_id, parts=parts_num + 1, name="idk.bin", md5_checksum=checksum),
            mime_type="application/octet-stream",
            attributes=[],
        ),
    ))

    assert isinstance(result, MessageMediaDocument)
    doc = result.document
    assert isinstance(doc, Document)

    part_num = 0
    length = 1024 * 1024
    async for chunk in _stream_download(client, doc):
        offset = length * part_num
        part_num += 1
        assert chunk == file_content[offset:offset + length]


@pytest.mark.asyncio
async def test_save_file_part_negative_part_id(client_with_auth: ClientFactory) -> None:
    client = await client_with_auth(run=True)
    file_id = client.rnd_id()

    part = os.urandom(1024)

    with pytest.raises(FilePartInvalid):
        await client.invoke(SaveFilePart(file_id=file_id, file_part=-1, bytes=part))


@pytest.mark.asyncio
async def test_save_file_part_too_big(client_with_auth: ClientFactory) -> None:
    client = await client_with_auth(run=True)
    file_id = client.rnd_id()

    part = os.urandom(1024)

    with pytest.raises(FilePartInvalid):
        await client.invoke(SaveFilePart(file_id=file_id, file_part=APP_CONFIG.upload_small_max_file_parts, bytes=part))


@pytest.mark.asyncio
async def test_save_big_file_part_negative_part_id(client_with_auth: ClientFactory) -> None:
    client = await client_with_auth(run=True)
    file_id = client.rnd_id()

    part = os.urandom(1024)

    with pytest.raises(FilePartInvalid):
        await client.invoke(SaveBigFilePart(file_id=file_id, file_part=-1, file_total_parts=3, bytes=part))


@pytest.mark.asyncio
async def test_save_big_file_part_too_big(client_with_auth: ClientFactory) -> None:
    client = await client_with_auth(run=True)
    file_id = client.rnd_id()

    part = os.urandom(1024)

    with pytest.raises(FilePartInvalid):
        await client.invoke(SaveBigFilePart(
            file_id=file_id, file_part=APP_CONFIG.upload_max_file_parts, file_total_parts=3, bytes=part,
        ))


@pytest.mark.asyncio
async def test_save_big_file_total_parts_too_big(client_with_auth: ClientFactory) -> None:
    client = await client_with_auth(run=True)
    file_id = client.rnd_id()

    part = os.urandom(1024)

    with pytest.raises(FilePartInvalid):
        await client.invoke(SaveBigFilePart(
            file_id=file_id, file_part=0, file_total_parts=APP_CONFIG.upload_max_file_parts + 1, bytes=part,
        ))


@pytest.mark.asyncio
async def test_save_file_part_reupload_only_part(client_with_auth: ClientFactory) -> None:
    client = await client_with_auth(run=True)
    file_id = client.rnd_id()

    part = os.urandom(1024)

    await client.invoke(SaveFilePart(file_id=file_id, file_part=0, bytes=part))
    await client.invoke(SaveFilePart(file_id=file_id, file_part=0, bytes=part))


# TODO: add tests for streaming uploads
# TODO: add tests for uploads where InputFile.parts/InputFileBig.parts is less than actual number of uploaded parts
