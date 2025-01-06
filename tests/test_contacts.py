import pytest

from tests.conftest import TestClient


@pytest.mark.asyncio
async def test_get_contacts() -> None:
    async with TestClient(phone_number="123456789") as client:
        assert await client.get_contacts() == []


@pytest.mark.asyncio
async def test_add_delete_contact() -> None:
    async with TestClient(phone_number="123456789") as client, TestClient(phone_number="1234567890") as client2:
        await client2.set_username("test2_username")
        me2 = await client2.get_me()
        user2 = await client.get_users("test2_username")

        assert await client.get_contacts() == []

        contact = await client.add_contact(user2.id, first_name="test", last_name="123")
        assert contact is not None
        assert contact.first_name == "test"
        assert contact.last_name == "123"
        assert contact.first_name != me2.first_name
        assert contact.last_name != me2.last_name

        assert len(await client.get_contacts()) == 1

        deleted_contact = await client.delete_contacts(user2.id)
        assert deleted_contact is not None
        assert deleted_contact.first_name == me2.first_name
        assert deleted_contact.last_name == me2.last_name

        assert await client.get_contacts() == []
