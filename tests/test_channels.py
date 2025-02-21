import pytest

from tests.conftest import TestClient


@pytest.mark.asyncio
async def test_create_channel() -> None:
    async with TestClient(phone_number="123456789") as client:
        channel = await client.create_channel("idk")
        assert channel.title == "idk"


@pytest.mark.asyncio
async def test_edit_channel_title() -> None:
    async with TestClient(phone_number="123456789") as client:
        channel = await client.create_channel("idk")
        assert channel.title == "idk"

        assert await channel.set_title("new title")
        channel2 = await client.get_chat(channel.id)
        assert channel2.title == "new title"
