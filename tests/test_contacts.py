from base64 import urlsafe_b64encode, urlsafe_b64decode
from contextlib import AsyncExitStack
from os import urandom

import pytest
from pyrogram.errors import PeerIdInvalid, BadRequest
from pyrogram.raw.functions.account import DeleteAccount
from pyrogram.raw.functions.contacts import Search, ImportContactToken
from pyrogram.raw.types import PeerUser
from pyrogram.utils import get_channel_id

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


@pytest.mark.asyncio
async def test_contact_token_import_export(exit_stack: AsyncExitStack) -> None:
    client1: TestClient = await exit_stack.enter_async_context(TestClient(phone_number="123456789"))
    client2: TestClient = await exit_stack.enter_async_context(TestClient(phone_number="123456780"))

    with pytest.raises(PeerIdInvalid):
        await client1.get_users(client2.me.id)

    user2_for_1_imported = await client1.resolve_user(client2)
    assert user2_for_1_imported.id == client2.me.id
    user2_for_1 = await client1.get_users(client2.me.id)
    assert user2_for_1 == user2_for_1_imported

    with pytest.raises(PeerIdInvalid):
        await client2.get_users(client1.me.id)

    user1_for_2_imported = await client2.resolve_user(client1)
    assert user1_for_2_imported.id == client1.me.id
    user1_for_2 = await client2.get_users(client1.me.id)
    assert user1_for_2 == user1_for_2_imported


@pytest.mark.asyncio
async def test_contact_token_import_export_self(exit_stack: AsyncExitStack) -> None:
    client: TestClient = await exit_stack.enter_async_context(TestClient(phone_number="123456789"))

    user_imported = await client.resolve_user(client)
    assert client.me == user_imported


@pytest.mark.asyncio
async def test_contact_token_import_invalid(exit_stack: AsyncExitStack) -> None:
    client: TestClient = await exit_stack.enter_async_context(TestClient(phone_number="123456789"))
    with pytest.raises(BadRequest):
        await client.invoke(ImportContactToken(token="invalid token"))


@pytest.mark.asyncio
async def test_contact_token_import_invalid_length(exit_stack: AsyncExitStack) -> None:
    client1: TestClient = await exit_stack.enter_async_context(TestClient(phone_number="123456789"))
    client2: TestClient = await exit_stack.enter_async_context(TestClient(phone_number="123456780"))

    exported_token = await client2.export_contact_token()
    valid_contact_token = TestClient.parse_contact_token_url(exported_token)

    contact_token = urlsafe_b64encode(urandom(1) + urlsafe_b64decode(valid_contact_token)).decode("ascii")
    with pytest.raises(BadRequest):
        await client1.invoke(ImportContactToken(token=contact_token))

    contact_token = urlsafe_b64encode(urlsafe_b64decode(valid_contact_token)[1:]).decode("ascii")
    with pytest.raises(BadRequest):
        await client1.invoke(ImportContactToken(token=contact_token))


@pytest.mark.asyncio
async def test_contact_token_import_invalid_signature(exit_stack: AsyncExitStack) -> None:
    client1: TestClient = await exit_stack.enter_async_context(TestClient(phone_number="123456789"))
    client2: TestClient = await exit_stack.enter_async_context(TestClient(phone_number="123456780"))

    exported_token = await client2.export_contact_token()
    contact_token_bytes = urlsafe_b64decode(TestClient.parse_contact_token_url(exported_token))

    invalid_token_bytes = bytes([(contact_token_bytes[0] + 1) % 256]) + contact_token_bytes[1:]
    invalid_contact_token = urlsafe_b64encode(invalid_token_bytes).decode("ascii")
    with pytest.raises(BadRequest):
        await client1.invoke(ImportContactToken(token=invalid_contact_token))

    invalid_token_bytes = contact_token_bytes[:-1] + bytes([(contact_token_bytes[-1] + 1) % 256])
    invalid_contact_token = urlsafe_b64encode(invalid_token_bytes).decode("ascii")
    with pytest.raises(BadRequest):
        await client1.invoke(ImportContactToken(token=invalid_contact_token))


@pytest.mark.asyncio
async def test_contact_token_import_deleted_user(exit_stack: AsyncExitStack) -> None:
    client1: TestClient = await exit_stack.enter_async_context(TestClient(phone_number="123456789"))
    client2: TestClient = await exit_stack.enter_async_context(TestClient(phone_number="123456780"))

    exported_token = await client2.export_contact_token()
    contact_token = TestClient.parse_contact_token_url(exported_token)

    await client2.invoke(DeleteAccount(reason="testing"))

    with pytest.raises(BadRequest):
        await client1.invoke(ImportContactToken(token=contact_token))
