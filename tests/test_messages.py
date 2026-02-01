from asyncio import get_running_loop
from contextlib import AsyncExitStack
from datetime import timedelta, datetime, UTC
from io import BytesIO
from time import time

import pytest
from PIL import Image
from fastrand import xorshift128plus_bytes
from loguru import logger
from pyrogram.enums import MessageEntityType
from pyrogram.errors import NotAcceptable, Forbidden
from pyrogram.raw.functions.channels import GetMessages as GetMessagesChannel, SetDiscussionGroup
from pyrogram.raw.functions.messages import GetHistory, DeleteHistory, GetMessages, GetUnreadMentions, ReadMentions, \
    GetSearchResultsCalendar, EditMessage, DeleteScheduledMessages, SetHistoryTTL, SaveDraft
from pyrogram.raw.types import InputPeerSelf, InputMessageID, InputMessageReplyTo, InputChannel, \
    InputMessagesFilterPhotoVideo, UpdateNewMessage, UpdateDeleteScheduledMessages, UpdateDeleteMessages, \
    UpdateNewChannelMessage, UpdateEditChannelMessage, UpdateDraftMessage, DraftMessage, DraftMessageEmpty
from pyrogram.raw.types.messages import Messages, AffectedHistory, SearchResultsCalendar
from pyrogram.types import InputMediaDocument, ChatPermissions
from tortoise.expressions import F, Subquery

from piltover.db.enums import PeerType
from piltover.db.models import MessageRef, Peer, User, MessageContent
from piltover.tl import InputPrivacyKeyChatInvite, InputPrivacyValueAllowUsers
from tests.client import TestClient


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
async def test_send_message_with_big_file_to_self() -> None:
    async with TestClient(phone_number="123456789") as client:
        file = BytesIO(xorshift128plus_bytes(1024 * 1024 * 32))
        setattr(file, "name", "test.bin")
        message = await client.send_document("me", document=file)
        assert message.document is not None
        downloaded = await message.download(in_memory=True)
        assert downloaded.getvalue() == file.getvalue()


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
        assert len(messages) == 1
        assert messages[0].service

        message = await client.send_message(group.id, text="test 123456")
        assert message.text == "test 123456"

        messages = [msg async for msg in client.get_chat_history(group.id)]
        assert len(messages) == 2

        messages.sort(key=lambda msg: msg.id)
        assert messages[1].id == message.id
        assert messages[1].text == message.text
        assert messages[1].service is None


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

        await MessageContent.filter(
            id=Subquery(MessageRef.filter(id=message.id).first().values_list("content__id", flat=True))
        ).update(message="some another text 123456789")

        messages = [msg async for msg in client.get_chat_history("me")]
        assert len(messages) == 1

        assert messages[0].id == message.id
        # Text should be same because message is already cached and cache is based on "version" field
        assert messages[0].text == message.text

        await MessageRef.filter(id=message.id).update(version=F("version") + 1)

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
        assert len(messages) == 2

        messages.sort(key=lambda msg: msg.id)
        assert messages[1].id == message.id
        assert messages[1].text == message.text
        assert messages[1].service is None
        assert messages[0].service


@pytest.mark.asyncio
async def test_delete_history() -> None:
    async with TestClient(phone_number="123456789") as client:
        user = await User.get(id=client.me.id)
        peer, _ = await Peer.get_or_create(owner=user, type=PeerType.SELF)
        await MessageContent.bulk_create([
            MessageContent(author=user, message="test")
            for i in range(1500)
        ])
        await MessageRef.bulk_create([
            MessageRef(peer=peer, content=content)
            for content in await MessageContent.filter(author=user)
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

        await client2.set_privacy(
            InputPrivacyKeyChatInvite(),
            InputPrivacyValueAllowUsers(users=[await client2.resolve_peer("test1_username")]),
        )

        user1 = await client2.get_users("test1_username")
        user2 = await client1.get_users("test2_username")

        group = await client1.create_group("idk", [user2.id])

        assert await client2.send_message(group.id, "test 1")

        await client1.set_chat_permissions(group.id, ChatPermissions())

        assert await client1.send_message(group.id, "test 2.5")
        with pytest.raises(Forbidden):
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
        assert poll.total_voter_count == 0
        assert poll.options[0].voter_count == 0


@pytest.mark.asyncio
async def test_edit_message_with_document() -> None:
    async with TestClient(phone_number="123456789") as client:
        file = BytesIO(b"test document 1")
        setattr(file, "name", "test.txt")
        message = await client.send_document("me", document=file, caption="test caption")
        assert message.document is not None
        assert message.caption == "test caption"
        downloaded = await message.download(in_memory=True)
        assert downloaded.getvalue() == b"test document 1"

        new_file = BytesIO(b"test document 2")
        setattr(new_file, "name", f"test2.txt")
        real_guess_mime_type = client.guess_mime_type
        client.guess_mime_type = lambda _: "text/plain"
        new_message = await client.edit_message_media(
            "me", message.id, InputMediaDocument(new_file), file_name="test2.txt",
        )
        client.guess_mime_type = real_guess_mime_type
        assert new_message.document is not None
        assert new_message.caption is None
        downloaded = await new_message.download(in_memory=True)
        assert downloaded.getvalue() == b"test document 2"

        new_message = await client.edit_message_caption("me", message.id, "test caption 2")
        assert new_message.document is not None
        assert new_message.caption == "test caption 2"
        downloaded = await new_message.download(in_memory=True)
        assert downloaded.getvalue() == b"test document 2"


@pytest.mark.asyncio
async def test_mention_user_in_pm(exit_stack: AsyncExitStack) -> None:
    client1: TestClient = await exit_stack.enter_async_context(TestClient(phone_number="123456789"))
    client2: TestClient = await exit_stack.enter_async_context(TestClient(phone_number="1234567890"))

    await client1.set_username("test1_username")
    await client2.get_users("test1_username")

    await client2.set_username("test2_username")
    await client1.get_users("test2_username")

    message = await client1.send_message("test2_username", "test no mention")
    assert message
    assert not message.mentioned

    message = await client1.send_message("test2_username", "test @test2_username mention")
    assert message
    assert not message.mentioned

    messages = [message2 async for message2 in client2.get_chat_history("test1_username")]
    messages.sort(key=lambda m: m.id)
    assert messages
    assert len(messages) == 2
    assert not messages[0].mentioned
    assert not messages[1].mentioned


@pytest.mark.asyncio
async def test_get_unread_mentions_and_read_them_in_pm(exit_stack: AsyncExitStack) -> None:
    client1: TestClient = await exit_stack.enter_async_context(TestClient(phone_number="123456789"))
    client2: TestClient = await exit_stack.enter_async_context(TestClient(phone_number="1234567890"))

    await client1.set_username("test1_username")
    await client2.get_users("test1_username")

    await client2.set_username("test2_username")
    await client1.get_users("test2_username")

    assert await client1.send_message("test2_username", "test no mention")

    unread: Messages = await client2.invoke(GetUnreadMentions(
        peer=await client2.resolve_peer("test1_username"),
        offset_id=0,
        add_offset=0,
        limit=10,
        max_id=0,
        min_id=0,
    ))
    assert len(unread.messages) == 0

    assert await client1.send_message("test2_username", "test @test2_username mention")

    unread: Messages = await client2.invoke(GetUnreadMentions(
        peer=await client2.resolve_peer("test1_username"),
        offset_id=0,
        add_offset=0,
        limit=10,
        max_id=0,
        min_id=0,
    ))
    assert len(unread.messages) == 0

    assert await client2.invoke(ReadMentions(peer=await client2.resolve_peer("test1_username")))

    unread: Messages = await client2.invoke(GetUnreadMentions(
        peer=await client2.resolve_peer("test1_username"),
        offset_id=0,
        add_offset=0,
        limit=10,
        max_id=0,
        min_id=0,
    ))
    assert len(unread.messages) == 0


@pytest.mark.asyncio
async def test_mention_user_in_chat(exit_stack: AsyncExitStack) -> None:
    client1: TestClient = await exit_stack.enter_async_context(TestClient(phone_number="123456789"))
    client2: TestClient = await exit_stack.enter_async_context(TestClient(phone_number="1234567890"))

    await client1.set_username("test1_username")

    await client2.set_privacy(
        InputPrivacyKeyChatInvite(),
        InputPrivacyValueAllowUsers(users=[await client2.resolve_peer("test1_username")]),
    )

    await client2.set_username("test2_username")
    user2 = await client1.get_users("test2_username")

    group = await client1.create_group("idk", [user2.id])

    message = await client1.send_message(group.id, "test no mention")
    assert message
    assert not message.mentioned

    message = await client1.send_message(group.id, "test @test2_username mention")
    assert message
    assert not message.mentioned

    messages = [message2 async for message2 in client2.get_chat_history(group.id)]
    messages.sort(key=lambda m: m.id)
    assert messages
    assert len(messages) == 3
    assert not messages[1].mentioned
    assert messages[2].mentioned


@pytest.mark.asyncio
async def test_get_unread_mentions_and_read_them_in_chat(exit_stack: AsyncExitStack) -> None:
    client1: TestClient = await exit_stack.enter_async_context(TestClient(phone_number="123456789"))
    client2: TestClient = await exit_stack.enter_async_context(TestClient(phone_number="1234567890"))

    await client1.set_username("test1_username")

    await client2.set_privacy(
        InputPrivacyKeyChatInvite(),
        InputPrivacyValueAllowUsers(users=[await client2.resolve_peer("test1_username")]),
    )

    await client2.set_username("test2_username")
    user2 = await client1.get_users("test2_username")

    group = await client1.create_group("idk", [user2.id])

    assert await client1.send_message(group.id, "test no mention")

    unread: Messages = await client2.invoke(GetUnreadMentions(
        peer=await client2.resolve_peer(group.id),
        offset_id=0,
        add_offset=0,
        limit=10,
        max_id=0,
        min_id=0,
    ))
    assert len(unread.messages) == 0

    assert await client1.send_message(group.id, "test @test2_username mention")

    unread: Messages = await client2.invoke(GetUnreadMentions(
        peer=await client2.resolve_peer(group.id),
        offset_id=0,
        add_offset=0,
        limit=10,
        max_id=0,
        min_id=0,
    ))
    assert len(unread.messages) == 1

    assert await client2.invoke(ReadMentions(peer=await client2.resolve_peer(group.id)))

    unread: Messages = await client2.invoke(GetUnreadMentions(
        peer=await client2.resolve_peer(group.id),
        offset_id=0,
        add_offset=0,
        limit=10,
        max_id=0,
        min_id=0,
    ))
    assert len(unread.messages) == 0


@pytest.mark.asyncio
async def test_mention_user_in_chat_with_reply(exit_stack: AsyncExitStack) -> None:
    client1: TestClient = await exit_stack.enter_async_context(TestClient(phone_number="123456789"))
    client2: TestClient = await exit_stack.enter_async_context(TestClient(phone_number="1234567890"))

    await client1.set_username("test1_username")

    await client2.set_privacy(
        InputPrivacyKeyChatInvite(),
        InputPrivacyValueAllowUsers(users=[await client2.resolve_peer("test1_username")]),
    )

    await client2.set_username("test2_username")
    user2 = await client1.get_users("test2_username")

    group = await client1.create_group("idk", [user2.id])

    await client2.send_message(group.id, "test message")

    unread: Messages = await client2.invoke(GetUnreadMentions(
        peer=await client2.resolve_peer(group.id),
        offset_id=0,
        add_offset=0,
        limit=10,
        max_id=0,
        min_id=0,
    ))
    assert len(unread.messages) == 0

    reply_to = [m async for m in client1.get_chat_history(group.id)][0]

    message = await client1.send_message(group.id, "test reply", reply_to_message_id=reply_to.id)
    assert message
    assert not message.mentioned

    unread: Messages = await client2.invoke(GetUnreadMentions(
        peer=await client2.resolve_peer(group.id),
        offset_id=0,
        add_offset=0,
        limit=10,
        max_id=0,
        min_id=0,
    ))
    assert len(unread.messages) == 1

    messages = [message2 async for message2 in client2.get_chat_history(group.id)]
    messages.sort(key=lambda m: m.id)
    assert messages
    assert len(messages) == 3
    assert not messages[1].mentioned
    assert messages[2].mentioned


_test_get_search_results_calendar_dates = [
    datetime(2025, 1, 1, 15, 0, tzinfo=UTC),

    datetime(2025, 1, 10, 12, 0, tzinfo=UTC),
    datetime(2025, 1, 10, 12, 30, tzinfo=UTC),

    datetime(2025, 1, 20, 12, 0, tzinfo=UTC),

    datetime(2025, 1, 30, 12, 0, tzinfo=UTC),
    datetime(2025, 1, 30, 12, 1, tzinfo=UTC),
    datetime(2025, 1, 30, 12, 2, tzinfo=UTC),
]


async def _make_test_get_search_results_calendar_data(client: TestClient) -> list[int]:
    photo_file = BytesIO()
    Image.new(mode="RGB", size=(256, 256), color=(255, 255, 255)).save(photo_file, format="PNG")
    setattr(photo_file, "name", "photo.png")

    messages = [
        await client.send_message("me", "test message no photo"),

        await client.send_message("me", "test message no photo 2"),
        await client.send_photo("me", photo_file),

        await client.send_photo("me", photo_file),

        await client.send_photo("me", photo_file),
        await client.send_message("me", "test message no photo 3"),
        await client.send_photo("me", photo_file),
    ]

    for message, date in zip(messages, _test_get_search_results_calendar_dates):
        await MessageContent.filter(
            id=Subquery(MessageRef.filter(id=message.id).first().values_list("content__id", flat=True)),
        ).update(date=date)
        await MessageRef.filter(id=message.id).update(version=F("version") + 1)

    return [message.id for message in messages]


@pytest.mark.search_results_calendar
@pytest.mark.asyncio
async def test_get_search_results_calendar(exit_stack: AsyncExitStack) -> None:
    client: TestClient = await exit_stack.enter_async_context(TestClient(phone_number="123456789"))
    messages = await _make_test_get_search_results_calendar_data(client)
    dates = _test_get_search_results_calendar_dates

    result: SearchResultsCalendar = await client.invoke(GetSearchResultsCalendar(
        peer=await client.resolve_peer("me"),
        filter=InputMessagesFilterPhotoVideo(),
        offset_id=0,
        offset_date=0,
    ))

    assert len(result.periods) == 3
    assert result.count == 4
    assert result.min_msg_id == messages[0]
    assert result.min_date == int(dates[0].timestamp())

    assert result.periods[0].date == int(dates[-1].timestamp()) // 86400 * 86400
    assert result.periods[0].min_msg_id == messages[4]
    assert result.periods[0].max_msg_id == messages[6]

    assert result.periods[1].date == int(dates[3].timestamp()) // 86400 * 86400
    assert result.periods[1].min_msg_id == messages[3]
    assert result.periods[1].max_msg_id == messages[3]

    assert result.periods[2].date == int(dates[2].timestamp()) // 86400 * 86400
    assert result.periods[2].min_msg_id == messages[2]
    assert result.periods[2].max_msg_id == messages[2]


@pytest.mark.search_results_calendar
@pytest.mark.asyncio
async def test_get_search_results_calendar_offset_last_media(exit_stack: AsyncExitStack) -> None:
    client: TestClient = await exit_stack.enter_async_context(TestClient(phone_number="123456789"))
    messages = await _make_test_get_search_results_calendar_data(client)
    dates = _test_get_search_results_calendar_dates

    result: SearchResultsCalendar = await client.invoke(GetSearchResultsCalendar(
        peer=await client.resolve_peer("me"),
        filter=InputMessagesFilterPhotoVideo(),
        offset_id=messages[6],
        offset_date=0,
    ))

    assert len(result.periods) == 3
    assert result.count == 4
    assert result.offset_id_offset == 1
    assert result.min_msg_id == messages[0]
    assert result.min_date == int(dates[0].timestamp())

    assert result.periods[0].date == int(dates[-1].timestamp()) // 86400 * 86400
    assert result.periods[0].min_msg_id == messages[4]
    assert result.periods[0].max_msg_id == messages[4]

    assert result.periods[1].date == int(dates[3].timestamp()) // 86400 * 86400
    assert result.periods[1].min_msg_id == messages[3]
    assert result.periods[1].max_msg_id == messages[3]

    assert result.periods[2].date == int(dates[2].timestamp()) // 86400 * 86400
    assert result.periods[2].min_msg_id == messages[2]
    assert result.periods[2].max_msg_id == messages[2]


@pytest.mark.search_results_calendar
@pytest.mark.asyncio
async def test_get_search_results_calendar_offset_first_for_day_media(exit_stack: AsyncExitStack) -> None:
    client: TestClient = await exit_stack.enter_async_context(TestClient(phone_number="123456789"))
    messages = await _make_test_get_search_results_calendar_data(client)
    dates = _test_get_search_results_calendar_dates

    result: SearchResultsCalendar = await client.invoke(GetSearchResultsCalendar(
        peer=await client.resolve_peer("me"),
        filter=InputMessagesFilterPhotoVideo(),
        offset_id=messages[4],
        offset_date=0,
    ))

    assert len(result.periods) == 2
    assert result.count == 4
    assert result.offset_id_offset == 2
    assert result.min_msg_id == messages[0]
    assert result.min_date == int(dates[0].timestamp())

    assert result.periods[0].date == int(dates[3].timestamp()) // 86400 * 86400
    assert result.periods[0].min_msg_id == messages[3]
    assert result.periods[0].max_msg_id == messages[3]

    assert result.periods[1].date == int(dates[2].timestamp()) // 86400 * 86400
    assert result.periods[1].min_msg_id == messages[2]
    assert result.periods[1].max_msg_id == messages[2]


@pytest.mark.run_scheduler
@pytest.mark.asyncio
async def test_send_scheduled_message(exit_stack: AsyncExitStack) -> None:
    client: TestClient = await exit_stack.enter_async_context(TestClient(phone_number="123456789"))

    await client.send_message("me", "test 123", schedule_date=datetime.now() + timedelta(seconds=3))

    messages = [m async for m in client.get_chat_history("me")]
    assert len(messages) == 0
    assert await client.get_chat_history_count("me") == 0

    update = await client.expect_update(UpdateNewMessage, 4)
    assert update.message.from_scheduled
    assert update.message.message == "test 123"

    await client.expect_update(UpdateDeleteScheduledMessages, .1)

    messages = [m async for m in client.get_chat_history("me")]
    assert len(messages) == 1
    assert await client.get_chat_history_count("me") == 1


@pytest.mark.run_scheduler
@pytest.mark.asyncio
async def test_edit_scheduled_message_date(exit_stack: AsyncExitStack) -> None:
    client: TestClient = await exit_stack.enter_async_context(TestClient(phone_number="123456789"))

    message = await client.send_message("me", "test 123", schedule_date=datetime.now() + timedelta(minutes=30))

    messages = [m async for m in client.get_chat_history("me")]
    assert len(messages) == 0
    assert await client.get_chat_history_count("me") == 0

    await client.invoke(EditMessage(
        peer=await client.resolve_peer("me"),
        id=message.id,
        schedule_date=int(time()),
    ))

    update = await client.expect_update(UpdateNewMessage, 1)
    assert update.message.from_scheduled
    assert update.message.message == "test 123"

    await client.expect_update(UpdateDeleteScheduledMessages, .1)

    messages = [m async for m in client.get_chat_history("me")]
    assert len(messages) == 1
    assert await client.get_chat_history_count("me") == 1


@pytest.mark.run_scheduler
@pytest.mark.asyncio
async def test_delete_scheduled_message(exit_stack: AsyncExitStack) -> None:
    client: TestClient = await exit_stack.enter_async_context(TestClient(phone_number="123456789"))

    message = await client.send_message("me", "test 123", schedule_date=datetime.now() + timedelta(seconds=1))

    await client.invoke(DeleteScheduledMessages(
        peer=await client.resolve_peer("me"),
        id=[message.id],
    ))

    await client.expect_update(UpdateDeleteScheduledMessages, 0.5)

    with pytest.raises(TimeoutError):
        await client.expect_update(UpdateNewMessage, 2)


@pytest.mark.run_scheduler
@pytest.mark.asyncio
async def test_messages_ttl(exit_stack: AsyncExitStack) -> None:
    MessageContent.TTL_MULT = 1

    client: TestClient = await exit_stack.enter_async_context(TestClient(phone_number="123456789"))

    group = await client.create_group("idk", [])
    message1 = await client.send_message(group.id, "test message that wont be deleted")

    await client.invoke(SetHistoryTTL(
        peer=await client.resolve_peer(group.id),
        period=86400 * 1,
    ))

    message2 = await client.send_message(group.id, "test message that WILL be deleted")

    await client.invoke(SetHistoryTTL(
        peer=await client.resolve_peer(group.id),
        period=0,
    ))

    update = await client.expect_update(UpdateDeleteMessages, 1.5)
    assert update.messages == [message2.id]

    message3 = await client.send_message(group.id, "test message 2 that wont be deleted")

    message_ids = [m.id async for m in client.get_chat_history(group.id)]
    assert message1.id in message_ids
    assert message2.id not in message_ids
    assert message3.id in message_ids


@pytest.mark.run_scheduler
@pytest.mark.asyncio
async def test_send_multiple_scheduled_messages(exit_stack: AsyncExitStack) -> None:
    client: TestClient = await exit_stack.enter_async_context(TestClient(phone_number="123456789"))

    now = datetime.now()
    await client.send_message("me", "test 123", schedule_date=now + timedelta(seconds=2))
    await client.send_message("me", "test 456", schedule_date=now + timedelta(seconds=3))
    await client.send_message("me", "test 789", schedule_date=now + timedelta(seconds=4))

    messages = [m async for m in client.get_chat_history("me")]
    assert len(messages) == 0
    assert await client.get_chat_history_count("me") == 0

    update1 = await client.expect_update(UpdateNewMessage, 4)
    assert update1.message.from_scheduled
    assert update1.message.message == "test 123"
    update2 = await client.expect_update(UpdateNewMessage, 2)
    assert update2.message.from_scheduled
    assert update2.message.message == "test 456"
    update3 = await client.expect_update(UpdateNewMessage, 2)
    assert update3.message.from_scheduled
    assert update3.message.message == "test 789"

    await client.expect_updates(
        UpdateDeleteScheduledMessages,
        UpdateDeleteScheduledMessages,
        UpdateDeleteScheduledMessages,
        timeout_per_update=.1,
    )

    messages = [m async for m in client.get_chat_history("me")]
    assert len(messages) == 3
    assert await client.get_chat_history_count("me") == 3


@pytest.mark.asyncio
async def test_messages_noforwards(exit_stack: AsyncExitStack) -> None:
    client: TestClient = await exit_stack.enter_async_context(TestClient(phone_number="123456789"))

    group = await client.create_group("idk", [])
    message1 = await client.send_message(group.id, "test message that wont have noforwards")

    assert await client.get_chat_history_count("me") == 0
    assert await client.forward_messages("me", group.id, message1.id)
    assert await client.get_chat_history_count("me") == 1

    await client.set_chat_protected_content(group.id, True)
    message2 = await client.send_message(group.id, "test message that WILL have noforwards")

    with pytest.raises(NotAcceptable, match="CHAT_FORWARDS_RESTRICTED"):
        assert await client.forward_messages("me", group.id, message1.id)
    assert await client.get_chat_history_count("me") == 1

    with pytest.raises(NotAcceptable, match="CHAT_FORWARDS_RESTRICTED"):
        assert await client.forward_messages("me", group.id, message2.id)
    assert await client.get_chat_history_count("me") == 1

    await client.set_chat_protected_content(group.id, False)

    assert await client.forward_messages("me", group.id, message1.id)
    assert await client.get_chat_history_count("me") == 2

    with pytest.raises(NotAcceptable, match="CHAT_FORWARDS_RESTRICTED"):
        assert await client.forward_messages("me", group.id, message2.id)
    assert await client.get_chat_history_count("me") == 2


@pytest.mark.asyncio
async def test_send_geo_in_pm(exit_stack: AsyncExitStack) -> None:
    client1: TestClient = await exit_stack.enter_async_context(TestClient(phone_number="123456789"))
    client2: TestClient = await exit_stack.enter_async_context(TestClient(phone_number="1234567890"))

    await client2.set_username("test2_username")

    message = await client1.send_location("test2_username", latitude=42.42, longitude=24.24)
    assert message.location
    assert message.location.latitude == 42.42
    assert message.location.longitude == 24.24


@pytest.mark.asyncio
async def test_send_dice_to_self(exit_stack: AsyncExitStack) -> None:
    client: TestClient = await exit_stack.enter_async_context(TestClient(phone_number="123456789"))

    for dice_emoji in ("🎲", "🎯", "🏀", "⚽", "🎳", "🎰"):
        message = await client.send_dice("me", dice_emoji)
        assert message.dice is not None
        assert message.dice.emoji == dice_emoji
        assert message.dice.value >= 1
        assert message.dice.value <= 64 if dice_emoji == "🎰" else 6


@pytest.mark.asyncio
async def test_send_message_to_channel_with_discussion_group(exit_stack: AsyncExitStack) -> None:
    client: TestClient = await exit_stack.enter_async_context(TestClient(phone_number="123456789"))

    channel = await client.create_channel("idk channel")
    group = await client.create_supergroup("idk group")

    await client.invoke(SetDiscussionGroup(
        broadcast=await client.resolve_peer(channel.id),
        group=await client.resolve_peer(group.id),
    ))

    async with client.expect_updates_m(UpdateNewChannelMessage, timeout_per_update=1):
        message = await client.send_message(channel.id, "test message")

    await client.expect_updates(UpdateEditChannelMessage, timeout_per_update=1)

    async for msg in client.get_chat_history(group.id, limit=1):
        assert msg.text == message.text
        assert msg.forward_from_message_id == message.id
        assert msg.forward_from_chat == channel
        break
    else:
        assert False


@pytest.mark.asyncio
async def test_send_message_to_channel_comments(exit_stack: AsyncExitStack) -> None:
    client: TestClient = await exit_stack.enter_async_context(TestClient(phone_number="123456789"))

    channel = await client.create_channel("idk channel")
    group = await client.create_supergroup("idk group")

    await client.invoke(SetDiscussionGroup(
        broadcast=await client.resolve_peer(channel.id),
        group=await client.resolve_peer(group.id),
    ))

    async with client.expect_updates_m(UpdateNewChannelMessage, timeout_per_update=1):
        message = await client.send_message(channel.id, "test message")

    await client.expect_updates(UpdateEditChannelMessage, timeout_per_update=1)

    discussion_message = await client.get_discussion_message(channel.id, message.id)
    assert len([m async for m in client.get_discussion_replies(discussion_message.chat.id, discussion_message.id)]) == 0

    comment = await discussion_message.reply("idk")

    async for msg in client.get_chat_history(group.id, limit=1):
        assert msg.text == comment.text
        assert msg.id == comment.id
        break
    else:
        assert False

    assert len([m async for m in client.get_discussion_replies(discussion_message.chat.id, discussion_message.id)]) == 1

    async for msg in client.get_discussion_replies(discussion_message.chat.id, discussion_message.id, limit=1):
        assert msg.text == comment.text
        assert msg.id == comment.id
        break
    else:
        assert False


@pytest.mark.asyncio
async def test_save_clear_draft(exit_stack: AsyncExitStack) -> None:
    client: TestClient = await exit_stack.enter_async_context(TestClient(phone_number="123456789"))

    await client.invoke(SaveDraft(
        peer=await client.resolve_peer("self"),
        message="asd qwe",
    ))
    update = await client.expect_update(UpdateDraftMessage)
    assert update.peer.user_id == client.me.id
    assert isinstance(update.draft, DraftMessage)
    assert update.draft.message == "asd qwe"

    await client.invoke(SaveDraft(
        peer=await client.resolve_peer("self"),
        message="",
    ))
    update = await client.expect_update(UpdateDraftMessage)
    assert update.peer.user_id == client.me.id
    assert isinstance(update.draft, DraftMessageEmpty)

