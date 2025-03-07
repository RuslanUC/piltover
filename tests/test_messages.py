from datetime import timedelta
from io import BytesIO

import pytest
from pyrogram.enums import MessageEntityType
from pyrogram.errors import ChatWriteForbidden
from pyrogram.raw.functions.messages import GetHistory, DeleteHistory, GetMessages
from pyrogram.raw.functions.channels import GetMessages as GetMessagesChannel
from pyrogram.raw.types import InputPeerSelf, InputMessageID, InputMessageReplyTo, InputChannel
from pyrogram.raw.types.messages import Messages, AffectedHistory
from pyrogram.types import InputMediaDocument, ChatPermissions

from piltover.db.enums import PeerType
from piltover.db.models import Message, FileAccess, Peer, User
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
    async with TestClient(phone_number="123456789") as client1, TestClient(phone_number="1234567890") as client2:
        await client2.set_username("client2_username")

        messages = [msg async for msg in client1.get_chat_history("client2_username")]
        assert len(messages) == 0

        message = await client1.send_message("client2_username", text="test 123456")
        assert message.text == "test 123456"

        messages = [msg async for msg in client1.get_chat_history("client2_username")]
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


@pytest.mark.asyncio
async def test_reply_to_message_in_chat_with_self() -> None:
    async with TestClient(phone_number="123456789") as client:
        message = await client.send_message("me", text="test 123")
        assert message.text == "test 123"
        rep_message = await message.reply("test reply", quote=True)
        assert rep_message is not None
        assert rep_message.text == "test reply"
        assert rep_message.reply_to_message_id == message.id


@pytest.mark.asyncio
async def test_gethistory_offsets() -> None:
    async with TestClient(phone_number="123456789") as client:
        for i in range(30):
            message = await client.send_message("me", text=f"test {i}")
            assert message.id == i + 1
            
        request = GetHistory(
            peer=InputPeerSelf(), offset_date=0, max_id=0, min_id=0, hash=0, limit=100, offset_id=0, add_offset=0,
        )

        messages: Messages = await client.invoke(request)
        assert len(messages.messages) == 30
        assert {message.id for message in messages.messages} == set(range(1, 31))

        request.offset_id = 25
        request.limit = 10
        messages: Messages = await client.invoke(request)
        assert len(messages.messages) == 10
        assert {message.id for message in messages.messages} == set(range(15, 24 + 1))

        request.offset_id = 25
        request.limit = 10
        request.add_offset = 5
        messages: Messages = await client.invoke(request)
        assert len(messages.messages) == 10
        assert {message.id for message in messages.messages} == set(range(10, 19 + 1))

        request.offset_id = 25
        request.limit = 10
        request.add_offset = -5
        messages: Messages = await client.invoke(request)
        assert len(messages.messages) == 10
        assert {message.id for message in messages.messages} == set(range(20, 29 + 1))


@pytest.mark.asyncio
async def test_send_message_in_channel() -> None:
    async with TestClient(phone_number="123456789") as client:
        channel = await client.create_channel("idk")

        message = await client.send_message(channel.id, "test message 123")
        assert message.text == "test message 123"

        messages = [msg async for msg in client.get_chat_history(channel.id)]
        assert len(messages) == 1

        assert messages[0].id == message.id
        assert messages[0].text == message.text


@pytest.mark.asyncio
async def test_delete_history() -> None:
    async with TestClient(phone_number="123456789") as client:
        user = await User.get(id=client.me.id)
        peer, _ = await Peer.get_or_create(owner=user, type=PeerType.SELF)
        await Message.bulk_create([
            Message(peer=peer, author=user, internal_id=i, message="test")
            for i in range(1500)
        ])

        assert await client.get_chat_history_count("me") == 1500

        result: AffectedHistory = await client.invoke(DeleteHistory(
            peer=await client.resolve_peer("me"),
            max_id=0,
        ))

        assert result.pts_count == 1000
        assert result.offset > 0

        assert await client.get_chat_history_count("me") == 500

        result: AffectedHistory = await client.invoke(DeleteHistory(
            peer=await client.resolve_peer("me"),
            max_id=result.offset,
        ))

        assert result.pts_count == 500
        assert result.offset == 0

        assert await client.get_chat_history_count("me") == 0


@pytest.mark.asyncio
async def test_edit_text_message_in_channel() -> None:
    async with TestClient(phone_number="123456789") as client:
        channel = await client.create_channel("idk")
        assert channel

        message = await client.send_message(channel.id, text="test 123")
        assert message.text == "test 123"

        new_message = await message.edit("test edited")

        assert new_message.id == message.id
        assert new_message.text == "test edited"


@pytest.mark.asyncio
async def test_getmessages() -> None:
    async with TestClient(phone_number="123456789") as client:
        message_1 = await client.send_message("me", text="1")
        assert message_1
        message_2 = await client.send_message("me", text="2", reply_to_message_id=message_1.id)
        assert message_2
        assert message_2.reply_to_message_id == message_1.id

        messages: Messages = await client.invoke(GetMessages(id=[InputMessageID(id=message_2.id)]))
        assert len(messages.messages) == 1
        assert messages.messages[0].id == message_2.id

        messages: Messages = await client.invoke(GetMessages(id=[InputMessageReplyTo(id=message_2.id)]))
        assert len(messages.messages) == 1
        assert messages.messages[0].id == message_1.id


@pytest.mark.asyncio
async def test_getmessages_in_channel() -> None:
    async with TestClient(phone_number="123456789") as client:
        channel = await client.create_channel("idk")
        assert channel

        message_1 = await client.send_message(channel.id, text="1")
        assert message_1
        message_2 = await client.send_message(channel.id, text="2", reply_to_message_id=message_1.id)
        assert message_2
        assert message_2.reply_to_message_id == message_1.id

        channel_peer = await client.resolve_peer(channel.id)
        input_channel = InputChannel(channel_id=channel_peer.channel_id, access_hash=channel_peer.access_hash)

        messages: Messages = await client.invoke(GetMessagesChannel(
            channel=input_channel,
            id=[InputMessageID(id=message_2.id)],
        ))
        assert len(messages.messages) == 1
        assert messages.messages[0].id == message_2.id

        messages: Messages = await client.invoke(GetMessagesChannel(
            channel=input_channel,
            id=[InputMessageReplyTo(id=message_2.id)],
        ))
        assert len(messages.messages) == 1
        assert messages.messages[0].id == message_1.id

        message_3 = await client.send_message("me", text="3")
        assert message_3
        messages: Messages = await client.invoke(GetMessagesChannel(
            channel=input_channel,
            id=[InputMessageID(id=message_3.id)],
        ))
        assert len(messages.messages) == 0


@pytest.mark.asyncio
async def test_delete_message_in_channel() -> None:
    async with TestClient(phone_number="123456789") as client:
        channel = await client.create_channel("idk")
        assert channel

        message = await client.send_message(channel.id, text="1")
        assert message

        channel_peer = await client.resolve_peer(channel.id)
        input_channel = InputChannel(channel_id=channel_peer.channel_id, access_hash=channel_peer.access_hash)

        messages: Messages = await client.invoke(GetMessagesChannel(
            channel=input_channel,
            id=[InputMessageID(id=message.id)],
        ))
        assert len(messages.messages) == 1
        assert messages.messages[0].id == message.id

        await message.delete()

        messages: Messages = await client.invoke(GetMessagesChannel(
            channel=input_channel,
            id=[InputMessageID(id=message.id)],
        ))
        assert len(messages.messages) == 0


@pytest.mark.asyncio
async def test_send_message_banned_rights() -> None:
    async with TestClient(phone_number="123456789") as client1, TestClient(phone_number="1234567890") as client2:
        await client1.set_username("test1_username")
        await client2.set_username("test2_username")
        user1 = await client2.get_users("test1_username")
        user2 = await client1.get_users("test2_username")

        group = await client1.create_group("idk", [user2.id])

        assert await client2.send_message(group.id, "test 1")

        await client1.set_chat_permissions(group.id, ChatPermissions())

        assert await client1.send_message(group.id, "test 2.5")
        with pytest.raises(ChatWriteForbidden):
            await client2.send_message(group.id, "test 2")

        await client1.set_chat_permissions(group.id, ChatPermissions(
            can_send_messages=True,
        ))

        assert await client2.send_message(group.id, "test 3")


@pytest.mark.asyncio
async def test_message_poll() -> None:
    async with TestClient(phone_number="123456789") as client:
        message = await client.send_poll("me", "test poll", ["answer 1", "answer 2", "answer 3"])
        poll = await client.vote_poll("me", message.id, 0)
        assert poll.question == "test poll"
        assert len(poll.options) == 3
        assert not poll.allows_multiple_answers
        assert poll.total_voter_count == 1
        assert poll.options[0].voter_count == 1

        poll = await client.retract_vote("me", message.id)
        assert poll.total_voter_count is None
        assert poll.options[0].voter_count == 0
