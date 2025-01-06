import pytest

from tests.conftest import TestClient


@pytest.mark.asyncio
async def test_change_chat_title() -> None:
    async with TestClient(phone_number="123456789") as client:
        group = await client.create_group("idk", [])
        assert group.title == "idk"

        await client.set_chat_title(group.id, "test 123")
        group = await client.get_chat(group.id)
        assert group.title == "test 123"
