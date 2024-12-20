from io import BytesIO

import pytest
from PIL import Image

from tests.conftest import TestClient


@pytest.mark.asyncio
async def test_set_profile_photo() -> None:
    async with TestClient(phone_number="123456789") as client:
        photo = Image.new(mode="RGB", size=(256, 256), color=(255, 0, 0))
        photo_file = BytesIO()
        setattr(photo_file, "name", "photo.png")
        photo.save(photo_file, format="PNG")

        me = await client.get_me()
        assert me.photo is None

        assert await client.set_profile_photo(photo=photo_file)

        me = await client.get_me()
        assert me.photo is not None
