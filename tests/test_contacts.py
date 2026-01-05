import pytest
from pyrogram.raw.functions.contacts import Search
from pyrogram.raw.types import PeerUser
from pyrogram.utils import get_channel_id

from piltover.tl import UpdateChannel, UpdateNewChannelMessage
from tests.client import TestClient


@pytest.mark.asyncio
async def test_get_contacts_empty() -> None:
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


@pytest.mark.asyncio
async def test_contacts_search() -> None:
    async with TestClient(phone_number="123456789") as client, TestClient(phone_number="1234567890") as client2:
        await client2.set_username("test2_username")
        me2 = await client2.get_me()

        result = await client.invoke(Search(
            q="test2",
            limit=3,
        ))

        assert len(result.results) == 1
        assert result.results[0].user_id == me2.id


@pytest.mark.asyncio
async def test_contacts_search_with_channel() -> None:
    async with TestClient(phone_number="123456789") as client, TestClient(phone_number="1234567890") as client2:
        await client2.set_username("test2_username")
        me2 = await client2.get_me()

        channel = await client2.create_channel("idk")
        assert await client2.set_chat_username(channel.id, "test2_channel")
        actual_channel_id = get_channel_id(channel.id)

        result = await client.invoke(Search(
            q="test2",
            limit=3,
        ))

        assert len(result.results) == 2
        if isinstance(result.results[0], PeerUser):
            assert result.results[0].user_id == me2.id
            assert result.results[1].channel_id == actual_channel_id
        else:
            assert result.results[1].user_id == me2.id
            assert result.results[0].channel_id == actual_channel_id
