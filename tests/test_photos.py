from contextlib import AsyncExitStack
from io import BytesIO
from typing import cast

import pytest
from PIL import Image
from pyrogram.file_id import FileId
from pyrogram.raw.functions.photos import GetUserPhotos
from pyrogram.raw.types.photos import PhotosSlice
from pyrogram.types import Photo

from tests.client import TestClient
from tests.utils import color_is_near

PHOTO_COLOR = (255, 0, 0)
MULTIPLE_PHOTO_COLORS = [
    (0, 0, 0),
    (255, 0, 0),
    (0, 255, 0),
    (0, 0, 255),
    (255, 255, 0),
    (255, 0, 255),
    (0, 255, 255),
    (255, 255, 255),
]


def make_png(color: tuple[int, int, int] = PHOTO_COLOR, filename: str = "photo.png") -> BytesIO:
    photo = Image.new(mode="RGB", size=(256, 256), color=color)
    photo_file = BytesIO()
    setattr(photo_file, "name", filename)
    photo.save(photo_file, format="PNG")

    return photo_file


@pytest.mark.asyncio
async def test_set_profile_photo() -> None:
    async with TestClient(phone_number="123456789") as client:
        photo_file = make_png()

        me = await client.get_me()
        assert me.photo is None

        assert await client.set_profile_photo(photo=photo_file)

        me = await client.get_me()
        assert me.photo is not None

        downloaded_photo_file = await client.download_media(me.photo.big_file_id, in_memory=True)
        downloaded_photo_file.seek(0)
        downloaded_photo = Image.open(downloaded_photo_file)
        assert color_is_near(PHOTO_COLOR, cast(tuple[int, int, int], downloaded_photo.getpixel((0, 0))))


@pytest.mark.asyncio
async def test_set_multiple_profile_photos(exit_stack: AsyncExitStack) -> None:
    client: TestClient = await exit_stack.enter_async_context(TestClient(phone_number="123456789"))

    for color in MULTIPLE_PHOTO_COLORS:
        assert await client.set_profile_photo(photo=make_png(color))

    photos_count = await client.get_chat_photos_count("me")
    assert photos_count == len(MULTIPLE_PHOTO_COLORS)

    idx = len(MULTIPLE_PHOTO_COLORS) - 1
    async for photo in client.get_chat_photos("me"):
        downloaded_photo_file = cast(BytesIO, await client.download_media(photo.file_id, in_memory=True))
        downloaded_photo_file.seek(0)
        downloaded_photo = Image.open(downloaded_photo_file)
        pixel = cast(tuple[int, int, int], downloaded_photo.getpixel((0, 0)))
        assert color_is_near(MULTIPLE_PHOTO_COLORS[idx], pixel)

        idx -= 1


@pytest.mark.asyncio
async def test_set_multiple_profile_photos_refetch_single_with_negative_offset(exit_stack: AsyncExitStack) -> None:
    client: TestClient = await exit_stack.enter_async_context(TestClient(phone_number="123456789"))

    for color in MULTIPLE_PHOTO_COLORS:
        assert await client.set_profile_photo(photo=make_png(color))

    refetch_idx = len(MULTIPLE_PHOTO_COLORS) // 2

    ids = [FileId.decode(photo.file_id).media_id async for photo in client.get_chat_photos("me")][::-1]
    refetch_id = ids[refetch_idx]

    photos = await client.invoke(GetUserPhotos(
        user_id=await client.resolve_peer("me"),
        offset=-1,
        max_id=refetch_id,
        limit=1,
    ))

    assert isinstance(photos, PhotosSlice)
    assert photos.count == len(MULTIPLE_PHOTO_COLORS)
    assert len(photos.photos) == 1

    pyro_photo = Photo._parse(client, photos.photos[0])
    downloaded_photo_file = cast(BytesIO, await client.download_media(pyro_photo.file_id, in_memory=True))
    downloaded_photo_file.seek(0)
    downloaded_photo = Image.open(downloaded_photo_file)
    pixel = cast(tuple[int, int, int], downloaded_photo.getpixel((0, 0)))
    assert color_is_near(MULTIPLE_PHOTO_COLORS[refetch_idx], pixel)
