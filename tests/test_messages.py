from datetime import timedelta
from io import BytesIO

import pytest
from pyrogram.enums import MessageEntityType
from pyrogram.types import InputMediaDocument

from piltover.db.models import Message, FileAccess
from tests.conftest import TestClient


@pytest.mark.asyncio
async def test_send_text_message_to_self() -> None:
    async with TestClient(phone_number="123456789") as client:
        messages = [msg async for msg in client.get_chat_history("me")]
        assert len(messages) == 0

        message = await client.send_message("me", text="test 123")
        assert message.text == "test 123"

        messages = [msg async for msg in client.get_chat_history("me")]
        assert len(messages) == 1

        assert messages[0].id == message.id
        assert messages[0].text == message.text


@pytest.mark.asyncio
async def test_send_message_with_document_to_self() -> None:
    async with TestClient(phone_number="123456789") as client:
        file = BytesIO(b"test document")
        setattr(file, "name", "test.txt")
        message = await client.send_document("me", document=file)
        assert message.document is not None
        downloaded = await message.download(in_memory=True)
        assert downloaded.getvalue() == b"test document"


@pytest.mark.asyncio
async def test_edit_text_message_in_chat_with_self() -> None:
    async with TestClient(phone_number="123456789") as client:
        message = await client.send_message("me", text="test 123")
        assert message.text == "test 123"

        new_message = await message.edit("test edited")

        assert new_message.id == message.id
        assert new_message.text == "test edited"


@pytest.mark.asyncio
async def test_delete_text_message_in_chat_with_self() -> None:
    async with TestClient(phone_number="123456789") as client:
        messages = [msg async for msg in client.get_chat_history("me")]
        assert len(messages) == 0

        message = await client.send_message("me", text="test 123")
        assert message.text == "test 123"

        messages = [msg async for msg in client.get_chat_history("me")]
        assert len(messages) == 1

        assert messages[0].id == message.id
        assert messages[0].text == message.text

        await message.delete()

        messages = [msg async for msg in client.get_chat_history("me")]
        assert len(messages) == 0


@pytest.mark.asyncio
async def test_pin_message_both_sides_in_chat_with_self() -> None:
    async with TestClient(phone_number="123456789") as client:
        message = await client.send_message("me", text="test 123")
        assert message.text == "test 123"
        service_message = await message.pin(both_sides=True)
        assert service_message is not None


@pytest.mark.asyncio
async def test_pin_message_one_side_in_chat_with_self() -> None:
    async with TestClient(phone_number="123456789") as client:
        message = await client.send_message("me", text="test 123")
        assert message.text == "test 123"
        service_message = await message.pin(both_sides=False)
        assert service_message is None


@pytest.mark.asyncio
async def test_forward_message_in_chat_with_self() -> None:
    async with TestClient(phone_number="123456789") as client:
        message = await client.send_message("me", text="test 123")
        assert message.text == "test 123"
        fwd_message = await message.forward("me")
        assert fwd_message is not None


@pytest.mark.asyncio
async def test_send_text_message_in_group() -> None:
    async with TestClient(phone_number="123456789") as client:
        group = await client.create_group("idk", [])
        messages = [msg async for msg in client.get_chat_history(group.id)]
        assert len(messages) == 0

        message = await client.send_message(group.id, text="test 123456")
        assert message.text == "test 123456"

        messages = [msg async for msg in client.get_chat_history(group.id)]
        assert len(messages) == 1

        assert messages[0].id == message.id
        assert messages[0].text == message.text


@pytest.mark.asyncio
async def test_send_text_message_in_pm() -> None:
    async with TestClient(phone_number="123456789") as client, TestClient(phone_number="1234567890") as client2:
        await client2.set_username("client2_username")

        messages = [msg async for msg in client.get_chat_history("client2_username")]
        assert len(messages) == 0

        message = await client.send_message("client2_username", text="test 123456")
        assert message.text == "test 123456"

        messages = [msg async for msg in client.get_chat_history("client2_username")]
        assert len(messages) == 1

        assert messages[0].id == message.id
        assert messages[0].text == message.text


@pytest.mark.asyncio
async def test_send_text_message_to_blocked() -> None:
    async with TestClient(phone_number="123456789") as client1, TestClient(phone_number="1234567890") as client2:
        await client1.set_username("test1_username")
        await client2.set_username("test2_username")
        user1 = await client2.get_users("test1_username")
        user2 = await client1.get_users("test2_username")

        assert await client2.send_message(user1.username, "test 123 1")
        assert len([msg async for msg in client2.get_chat_history(user1.username)]) == 1
        assert len([msg async for msg in client1.get_chat_history(user2.username)]) == 1

        assert await client1.block_user(user2.username)

        assert await client2.send_message(user1.username, "test 123 2")
        assert len([msg async for msg in client2.get_chat_history(user1.username)]) == 2
        assert len([msg async for msg in client1.get_chat_history(user2.username)]) == 1

        assert await client1.unblock_user(user2.username)

        assert await client2.send_message(user1.username, "test 123 3")
        assert len([msg async for msg in client2.get_chat_history(user1.username)]) == 3
        assert len([msg async for msg in client1.get_chat_history(user2.username)]) == 2


@pytest.mark.asyncio
async def test_get_dialogs() -> None:
    async with TestClient(phone_number="123456789") as client1, TestClient(phone_number="1234567890") as client2:
        assert len([dialog async for dialog in client1.get_dialogs()]) == 0

        await client1.send_message("me", "test")
        assert len([dialog async for dialog in client1.get_dialogs()]) == 1

        await client2.set_username("test2_username")
        await client1.send_message("test2_username", "123")
        assert len([dialog async for dialog in client1.get_dialogs()]) == 2

        assert len([dialog async for dialog in client2.get_dialogs()]) == 1


@pytest.mark.asyncio
async def test_internal_message_cache() -> None:
    async with TestClient(phone_number="123456789") as client:
        messages = [msg async for msg in client.get_chat_history("me")]
        assert len(messages) == 0

        message = await client.send_message("me", text="test 123")
        assert message.text == "test 123"

        messages = [msg async for msg in client.get_chat_history("me")]
        assert len(messages) == 1

        assert messages[0].id == message.id
        assert messages[0].text == message.text

        await Message.filter(id=message.id).update(message="some another text 123456789")

        messages = [msg async for msg in client.get_chat_history("me")]
        assert len(messages) == 1

        assert messages[0].id == message.id
        # Text should be same because message is already cached and cache is based on "version" field
        assert messages[0].text == message.text

        await Message.filter(id=message.id).update(version=100)

        messages = [msg async for msg in client.get_chat_history("me")]
        assert len(messages) == 1

        assert messages[0].id == message.id
        assert messages[0].text != message.text
        assert messages[0].text == "some another text 123456789"


@pytest.mark.asyncio
async def test_some_entities() -> None:
    async with TestClient(phone_number="123456789") as client:
        messages = [msg async for msg in client.get_chat_history("me")]
        assert len(messages) == 0

        message = await client.send_message("me", text="test **123**")
        assert message.text == "test 123"
        assert len(message.entities) == 1
        assert message.entities[0].type == MessageEntityType.BOLD
        assert message.entities[0].length == 3

        messages = [msg async for msg in client.get_chat_history("me")]
        assert len(messages) == 1

        assert messages[0].id == message.id
        assert messages[0].text == message.text
        assert len(messages[0].entities) == 1
        assert messages[0].entities[0].type == MessageEntityType.BOLD
        assert messages[0].entities[0].length == 3


@pytest.mark.asyncio
async def test_internal_message_cache_media_renew() -> None:
    async with TestClient(phone_number="123456789") as client:
        messages = [msg async for msg in client.get_chat_history("me")]
        assert len(messages) == 0

        file = BytesIO(b"test document")
        setattr(file, "name", "test.txt")
        message = await client.send_document("me", document=file)
        assert message.document is not None
        file_access = await FileAccess.get_or_none(file__messagemedias__messages__id=message.id)
        assert file_access is not None
        file_access.expires -= timedelta(days=14)
        await file_access.save(update_fields=["expires"])
        access_expires_at = file_access.expires

        messages = [msg async for msg in client.get_chat_history("me")]
        assert len(messages) == 1

        assert messages[0].id == message.id
        await file_access.refresh_from_db()
        assert access_expires_at != file_access.expires
        access_expires_at = file_access.expires

        messages = [msg async for msg in client.get_chat_history("me")]
        assert len(messages) == 1
        assert messages[0].id == message.id
        await file_access.refresh_from_db()
        assert access_expires_at == file_access.expires


@pytest.mark.asyncio
async def test_send_media_group_to_self() -> None:
    async with TestClient(phone_number="123456789") as client:
        media: list[InputMediaDocument] = []
        for i in range(3):
            file = BytesIO(f"test document {i}".encode("utf8"))
            setattr(file, "name", f"test{i}.txt")
            media.append(InputMediaDocument(file))

        media[2].caption = "some caption"
        messages = await client.send_media_group("me", media)

        assert len(messages) == 3

        group_id = messages[0].media_group_id
        assert group_id

        for i, message in enumerate(messages):
            downloaded = await message.download(in_memory=True)
            assert downloaded.getvalue() == f"test document {i}".encode("utf8")
            assert message.caption == ("some caption" if i == 2 else None)
            assert message.media_group_id == group_id
