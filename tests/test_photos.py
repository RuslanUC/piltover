from io import BytesIO
from typing import cast

import pytest
from PIL import Image

from tests.conftest import TestClient, color_is_near

PHOTO_COLOR = (255, 0, 0)


@pytest.mark.asyncio
async def test_set_profile_photo() -> None:
    async with TestClient(phone_number="123456789") as client:
        photo = Image.new(mode="RGB", size=(256, 256), color=PHOTO_COLOR)
        photo_file = BytesIO()
        setattr(photo_file, "name", "photo.png")
        photo.save(photo_file, format="PNG")

        me = await client.get_me()
        assert me.photo is None

        assert await client.set_profile_photo(photo=photo_file)

        me = await client.get_me()
        assert me.photo is not None

        downloaded_photo_file = await client.download_media(me.photo.big_file_id, in_memory=True)
        downloaded_photo_file.seek(0)
        downloaded_photo = Image.open(downloaded_photo_file)
        assert color_is_near(PHOTO_COLOR, cast(tuple[int, int, int], downloaded_photo.getpixel((0, 0))))
