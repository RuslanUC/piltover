from contextlib import AsyncExitStack
from io import BytesIO
from typing import cast

import pytest
from PIL import Image
from pyrogram.errors import ChatWriteForbidden, UsernameOccupied, PasswordMissing, PasswordHashInvalid, \
    ChatAdminRequired, UserIdInvalid, PeerIdInvalid, ChannelPrivate
from pyrogram.raw.functions.account import GetPassword
from pyrogram.raw.functions.channels import EditCreator
from pyrogram.raw.types import UpdateChannel, UpdateUserName, UpdateNewChannelMessage, InputUser
from pyrogram.types import ChatMember, ChatPrivileges
from pyrogram.utils import compute_password_check

from piltover.tl import InputCheckPasswordEmpty
from tests.conftest import TestClient, color_is_near

PHOTO_COLOR = (0x00, 0xff, 0x80)


@pytest.mark.asyncio
async def test_create_channel() -> None:
    async with TestClient(phone_number="123456789") as client:
        async with client.expect_updates_m(UpdateChannel, UpdateNewChannelMessage):
            channel = await client.create_channel("idk")
        assert channel.title == "idk"


@pytest.mark.asyncio
async def test_edit_channel_title() -> None:
    async with TestClient(phone_number="123456789") as client:
        async with client.expect_updates_m(UpdateChannel, UpdateNewChannelMessage):
            channel = await client.create_channel("idk")
        assert channel.title == "idk"

        async with client.expect_updates_m(UpdateChannel):
            assert await channel.set_title("new title")
        channel2 = await client.get_chat(channel.id)
        assert channel2.title == "new title"


@pytest.mark.asyncio
async def test_change_channel_photo() -> None:
    async with TestClient(phone_number="123456789") as client:
        async with client.expect_updates_m(UpdateChannel, UpdateNewChannelMessage):
            channel = await client.create_channel("idk")
        assert channel.photo is None

        photo = Image.new(mode="RGB", size=(256, 256), color=PHOTO_COLOR)
        photo_file = BytesIO()
        setattr(photo_file, "name", "photo.png")
        photo.save(photo_file, format="PNG")

        await client.set_chat_photo(channel.id, photo=photo_file)
        await client.expect_update(UpdateChannel)
        channel = await client.get_chat(channel.id)
        assert channel.photo is not None

        downloaded_photo_file = await client.download_media(channel.photo.big_file_id, in_memory=True)
        downloaded_photo_file.seek(0)
        downloaded_photo = Image.open(downloaded_photo_file)
        assert color_is_near(PHOTO_COLOR, cast(tuple[int, int, int], downloaded_photo.getpixel((0, 0))))


@pytest.mark.asyncio
async def test_get_channel_participants_only_owner() -> None:
    async with TestClient(phone_number="123456789") as client:
        async with client.expect_updates_m(UpdateChannel, UpdateNewChannelMessage):
            channel = await client.create_channel("idk")
        assert channel

        participants: list[ChatMember] = [participant async for participant in client.get_chat_members(channel.id)]
        assert len(participants) == 1
        assert participants[0].user.id == client.me.id


@pytest.mark.asyncio
async def test_channel_invite_and_promote_user() -> None:
    async with TestClient(phone_number="123456789") as client1, TestClient(phone_number="1234567890") as client2:
        await client1.set_username("test1_username")
        await client2.set_username("test2_username")
        await client1.expect_update(UpdateUserName)
        await client2.expect_update(UpdateUserName)
        user1 = await client2.get_users("test1_username")
        user2 = await client1.get_users("test2_username")

        async with client1.expect_updates_m(UpdateChannel, UpdateNewChannelMessage):
            channel = await client1.create_channel("idk")
        assert channel

        invite_link = await channel.export_invite_link()
        await client2.join_chat(invite_link)
        await client2.expect_update(UpdateChannel)

        assert await client1.send_message(channel.id, "test message")
        await client1.expect_update(UpdateNewChannelMessage)
        await client2.expect_update(UpdateNewChannelMessage)

        with pytest.raises(ChatWriteForbidden):
            assert await client2.send_message(channel.id, "test message 2")

        await client1.promote_chat_member(channel.id, user2.id, ChatPrivileges(can_post_messages=True))

        assert await client2.send_message(channel.id, "test message 2")
        await client1.expect_update(UpdateNewChannelMessage)
        await client2.expect_update(UpdateNewChannelMessage)


@pytest.mark.asyncio
async def test_channel_add_user() -> None:
    async with TestClient(phone_number="123456789") as client1, TestClient(phone_number="1234567890") as client2:
        await client1.set_username("test1_username")
        await client2.set_username("test2_username")
        await client1.expect_update(UpdateUserName)
        await client2.expect_update(UpdateUserName)

        async with client1.expect_updates_m(UpdateChannel, UpdateNewChannelMessage):
            channel = await client1.create_channel("idk")
        assert channel

        assert await client1.get_chat_members_count(channel.id) == 1

        assert await client1.add_chat_members(channel.id, "test2_username")
        await client2.expect_update(UpdateChannel)
        channel2 = await client2.get_chat(channel.id)
        assert channel2.id == channel.id

        assert await client1.get_chat_members_count(channel.id) == 2


@pytest.mark.asyncio
async def test_change_channel_username() -> None:
    async with TestClient(phone_number="123456789") as client:
        async with client.expect_updates_m(UpdateChannel, UpdateNewChannelMessage):
            channel = await client.create_channel("idk")
        assert channel.username is None

        assert await client.set_chat_username(channel.id, "test_channel")
        await client.expect_update(UpdateChannel)
        channel = await client.get_chat(channel.id)
        assert channel.username == "test_channel"


@pytest.mark.asyncio
async def test_change_channel_username_to_occupied_by_user() -> None:
    async with TestClient(phone_number="123456789") as client:
        async with client.expect_updates_m(UpdateChannel, UpdateNewChannelMessage):
            channel = await client.create_channel("idk")
        assert channel.username is None

        async with client.expect_updates_m(UpdateUserName):
            await client.set_username("test_username")
        with pytest.raises(UsernameOccupied):
            await client.set_chat_username(channel.id, "test_username")


@pytest.mark.parametrize(
    ("password_set", "password_check", "before", "after", "expect_updates_after", "expected_exception"),
    [
        ("test_passw0rd", "test_passw0rd", (True, False), (False, True), True, None),
        (None, "test_passw0rd", (True, False), (True, False), False, PasswordMissing),
        ("test_passw0rd", "test_passw0rd-wrong", (True, False), (True, False), False, PasswordHashInvalid),
    ],
    ids=("success", "fail-no-password", "fail-wrong-password"),
)
@pytest.mark.asyncio
async def test_edit_channel_owner(
        exit_stack: AsyncExitStack, password_set: str | None, password_check: str, before: tuple[bool, bool],
        after: tuple[bool, bool], expect_updates_after: bool, expected_exception: type[Exception] | None,
) -> None:
    client1: TestClient = await exit_stack.enter_async_context(TestClient(phone_number="123456789"))
    client2: TestClient = await exit_stack.enter_async_context(TestClient(phone_number="123456780"))

    await client1.set_username("test1_username")
    await client2.set_username("test2_username")
    await client1.expect_update(UpdateUserName)
    await client2.expect_update(UpdateUserName)

    async with client1.expect_updates_m(UpdateChannel, UpdateNewChannelMessage):
        channel = await client1.create_channel("idk")
    assert channel

    await client1.add_chat_members(channel.id, "test2_username")
    await client2.expect_update(UpdateChannel)

    channel1 = await client1.get_chat(channel.id)
    assert channel1.is_creator is before[0]

    channel2 = await client2.get_chat(channel.id)
    assert channel2.is_creator is before[1]

    input_password = InputCheckPasswordEmpty()
    if password_set is not None:
        await client1.enable_cloud_password(password=password_set)
        input_password = compute_password_check(await client1.invoke(GetPassword()), password_check)

    request = EditCreator(
        channel=await client1.resolve_peer(channel.id),
        user_id=await client1.resolve_peer("test2_username"),
        password=input_password,
    )

    if expected_exception is None:
        assert await client1.invoke(request)
    else:
        with pytest.raises(expected_exception):
            await client1.invoke(request)

    if expect_updates_after:
        await client1.expect_update(UpdateChannel)
        await client2.expect_update(UpdateChannel)

    channel1 = await client1.get_chat(channel.id)
    assert channel1.is_creator is after[0]

    channel2 = await client2.get_chat(channel.id)
    assert channel2.is_creator is after[1]


@pytest.mark.asyncio
async def test_edit_channel_owner_fail_not_owner(exit_stack: AsyncExitStack) -> None:
    client1: TestClient = await exit_stack.enter_async_context(TestClient(phone_number="123456789"))
    client2: TestClient = await exit_stack.enter_async_context(TestClient(phone_number="123456780"))
    client3: TestClient = await exit_stack.enter_async_context(TestClient(phone_number="123456781"))

    async with client1.expect_updates_m(UpdateUserName), \
            client2.expect_updates_m(UpdateUserName), \
            client3.expect_updates_m(UpdateUserName):
        await client1.set_username("test1_username")
        await client2.set_username("test2_username")
        await client3.set_username("test3_username")

    async with client1.expect_updates_m(UpdateChannel, UpdateNewChannelMessage):
        channel = await client1.create_channel("idk")
    assert channel

    await client1.add_chat_members(channel.id, ["test2_username", "test3_username"])
    await client2.expect_update(UpdateChannel)
    await client3.expect_update(UpdateChannel)

    channel1 = await client1.get_chat(channel.id)
    assert channel1.is_creator
    channel2 = await client2.get_chat(channel.id)
    assert not channel2.is_creator
    channel3 = await client3.get_chat(channel.id)
    assert not channel3.is_creator

    await client2.enable_cloud_password(password="test_passw0rd")

    with pytest.raises(ChatAdminRequired):
        await client2.invoke(EditCreator(
            channel=await client2.resolve_peer(channel.id),
            user_id=await client2.resolve_peer("test3_username"),
            password=compute_password_check(await client2.invoke(GetPassword()), "test_passw0rd"),
        ))

    channel1 = await client1.get_chat(channel.id)
    assert channel1.is_creator
    channel2 = await client2.get_chat(channel.id)
    assert not channel2.is_creator
    channel3 = await client3.get_chat(channel.id)
    assert not channel3.is_creator


@pytest.mark.asyncio
async def test_edit_channel_owner_fail_invalid_user(exit_stack: AsyncExitStack) -> None:
    client1: TestClient = await exit_stack.enter_async_context(TestClient(phone_number="123456789"))

    async with client1.expect_updates_m(UpdateChannel, UpdateNewChannelMessage):
        channel = await client1.create_channel("idk")
    assert channel

    channel1 = await client1.get_chat(channel.id)
    assert channel1.is_creator

    await client1.enable_cloud_password(password="test_passw0rd")

    with pytest.raises(PeerIdInvalid):
        await client1.invoke(EditCreator(
            channel=await client1.resolve_peer(channel.id),
            user_id=InputUser(user_id=client1.me.id + 1, access_hash=123456789),
            password=compute_password_check(await client1.invoke(GetPassword()), "test_passw0rd"),
        ))

    channel1 = await client1.get_chat(channel.id)
    assert channel1.is_creator


@pytest.mark.asyncio
async def test_edit_channel_owner_fail_user_not_participant(exit_stack: AsyncExitStack) -> None:
    client1: TestClient = await exit_stack.enter_async_context(TestClient(phone_number="123456789"))
    client2: TestClient = await exit_stack.enter_async_context(TestClient(phone_number="123456780"))

    async with client2.expect_updates_m(UpdateUserName):
        await client2.set_username("test2_username")

    async with client1.expect_updates_m(UpdateChannel, UpdateNewChannelMessage):
        channel = await client1.create_channel("idk")
    assert channel

    channel1 = await client1.get_chat(channel.id)
    assert channel1.is_creator

    await client1.enable_cloud_password(password="test_passw0rd")

    with pytest.raises(UserIdInvalid):
        await client1.invoke(EditCreator(
            channel=await client1.resolve_peer(channel.id),
            user_id=await client1.resolve_peer("test2_username"),
            password=compute_password_check(await client1.invoke(GetPassword()), "test_passw0rd"),
        ))

    channel1 = await client1.get_chat(channel.id)
    assert channel1.is_creator


@pytest.mark.asyncio
async def test_edit_channel_owner_fail_not_user(exit_stack: AsyncExitStack) -> None:
    client1: TestClient = await exit_stack.enter_async_context(TestClient(phone_number="123456789"))

    async with client1.expect_updates_m(UpdateChannel, UpdateNewChannelMessage):
        channel = await client1.create_channel("idk")
    assert channel

    channel1 = await client1.get_chat(channel.id)
    assert channel1.is_creator

    await client1.enable_cloud_password(password="test_passw0rd")

    with pytest.raises(UserIdInvalid):
        await client1.invoke(EditCreator(
            channel=await client1.resolve_peer(channel.id),
            user_id=await client1.resolve_peer(channel.id),
            password=compute_password_check(await client1.invoke(GetPassword()), "test_passw0rd"),
        ))

    channel1 = await client1.get_chat(channel.id)
    assert channel1.is_creator


@pytest.mark.asyncio
async def test_delete_channel_success(exit_stack: AsyncExitStack) -> None:
    client1: TestClient = await exit_stack.enter_async_context(TestClient(phone_number="123456789"))
    client2: TestClient = await exit_stack.enter_async_context(TestClient(phone_number="123456780"))

    async with client2.expect_updates_m(UpdateUserName):
        await client2.set_username("test2_username")

    async with client1.expect_updates_m(UpdateChannel, UpdateNewChannelMessage):
        channel = await client1.create_channel("idk")
    assert channel

    await client1.add_chat_members(channel.id, "test2_username")
    await client2.expect_update(UpdateChannel)

    assert await client1.get_chat(channel.id)
    assert await client2.get_chat(channel.id)

    assert await client1.delete_channel(channel.id)
    await client1.expect_update(UpdateChannel)
    await client2.expect_update(UpdateChannel)

    with pytest.raises(ChannelPrivate):
        await client1.get_chat(channel.id)

    with pytest.raises(ChannelPrivate):
        await client2.get_chat(channel.id)


@pytest.mark.asyncio
async def test_delete_channel_fail_not_owner(exit_stack: AsyncExitStack) -> None:
    client1: TestClient = await exit_stack.enter_async_context(TestClient(phone_number="123456789"))
    client2: TestClient = await exit_stack.enter_async_context(TestClient(phone_number="123456780"))

    async with client2.expect_updates_m(UpdateUserName):
        await client2.set_username("test2_username")

    async with client1.expect_updates_m(UpdateChannel, UpdateNewChannelMessage):
        channel = await client1.create_channel("idk")
    assert channel

    await client1.add_chat_members(channel.id, "test2_username")
    await client2.expect_update(UpdateChannel)

    assert await client1.get_chat(channel.id)
    assert await client2.get_chat(channel.id)

    with pytest.raises(ChatAdminRequired):
        await client2.delete_channel(channel.id)

    assert await client1.get_chat(channel.id)
    assert await client2.get_chat(channel.id)


@pytest.mark.asyncio
async def test_channel_join(exit_stack: AsyncExitStack) -> None:
    client1: TestClient = await exit_stack.enter_async_context(TestClient(phone_number="123456789"))
    client2: TestClient = await exit_stack.enter_async_context(TestClient(phone_number="123456780"))

    await client2.set_username("test2_username")
    await client2.expect_update(UpdateUserName)

    async with client1.expect_updates_m(UpdateChannel, UpdateNewChannelMessage):
        channel = await client1.create_channel("idk")

    async with client1.expect_updates_m(UpdateChannel):
        await client1.set_chat_username(channel.id, "test_public_channel")

    assert await client1.get_chat_members_count(channel.id) == 1
    assert len([dialog async for dialog in client2.get_dialogs()]) == 0

    async with client2.expect_updates_m(UpdateChannel):
        channel2 = await client2.join_chat("test_public_channel")
    assert channel2

    assert channel.id == channel2.id

    assert await client1.get_chat_members_count(channel.id) == 2
    assert len([dialog async for dialog in client2.get_dialogs()]) == 1


@pytest.mark.asyncio
async def test_get_public_channel_messages_without_join(exit_stack: AsyncExitStack) -> None:
    client1: TestClient = await exit_stack.enter_async_context(TestClient(phone_number="123456789"))
    client2: TestClient = await exit_stack.enter_async_context(TestClient(phone_number="123456780"))

    await client2.set_username("test2_username")
    await client2.expect_update(UpdateUserName)

    async with client1.expect_updates_m(UpdateChannel, UpdateNewChannelMessage, UpdateChannel):
        channel = await client1.create_channel("idk")
        await client1.set_chat_username(channel.id, "test_public_channel")

    messages = [m async for m in client2.get_chat_history("test_public_channel")]
    assert len(messages) == 1
    assert messages[0].service
    assert await client2.get_chat_history_count("test_public_channel") == 1

    message = await client1.send_message("test_public_channel", "test 123")

    messages = [m async for m in client2.get_chat_history("test_public_channel")]
    assert len(messages) == 2
    messages.sort(key=lambda msg: msg.id)
    assert messages[1].id == message.id
    assert messages[1].text == message.text
    assert messages[1].service is None
