from contextlib import AsyncExitStack
from io import BytesIO
from typing import cast

import pytest
from PIL import Image
from faker import Faker
from pyrogram.errors import UsernameOccupied, PasswordMissing, PasswordHashInvalid, \
    ChatAdminRequired, UserIdInvalid, PeerIdInvalid, ChannelPrivate, Forbidden, InviteHashExpired, UsernameNotModified, \
    ChatTitleEmpty, ChatAboutTooLong
from pyrogram.raw.functions.account import GetPassword
from pyrogram.raw.functions.channels import EditCreator, DeleteHistory
from pyrogram.raw.types import UpdateChannel, UpdateUserName, UpdateNewChannelMessage, InputUser, \
    InputPrivacyKeyChatInvite, InputPrivacyValueAllowUsers, InputChannel, InputPeerChannel
from pyrogram.types import ChatMember, ChatPrivileges
from pyrogram.utils import compute_password_check, get_channel_id

from piltover.tl import InputCheckPasswordEmpty
from tests.client import TestClient
from tests.conftest import ClientFactory, ChannelWithClientsFactory
from tests.utils import color_is_near

PHOTO_COLOR = (0x00, 0xff, 0x80)


@pytest.mark.asyncio
async def test_create_channel(client_with_auth: ClientFactory, exit_stack: AsyncExitStack) -> None:
    client: TestClient = await exit_stack.enter_async_context(await client_with_auth())

    async with client.expect_updates_m(UpdateChannel, UpdateNewChannelMessage):
        channel = await client.create_channel("idk")

    assert channel.title == "idk"


@pytest.mark.asyncio
async def test_create_channel_empty_name(client_with_auth: ClientFactory, exit_stack: AsyncExitStack) -> None:
    client: TestClient = await exit_stack.enter_async_context(await client_with_auth())
    with pytest.raises(ChatTitleEmpty):
        await client.create_channel("")


@pytest.mark.asyncio
async def test_create_channel_name_too_long(client_with_auth: ClientFactory, exit_stack: AsyncExitStack) -> None:
    client: TestClient = await exit_stack.enter_async_context(await client_with_auth())
    with pytest.raises(ChatTitleEmpty):
        await client.create_channel("1234" * 16 + "1")


@pytest.mark.asyncio
async def test_create_channel_description_too_long(client_with_auth: ClientFactory, exit_stack: AsyncExitStack) -> None:
    client: TestClient = await exit_stack.enter_async_context(await client_with_auth())
    with pytest.raises(ChatAboutTooLong):
        await client.create_channel("test name", description="1234" * 64)


@pytest.mark.asyncio
async def test_edit_channel_title(channel_with_clients: ChannelWithClientsFactory, exit_stack: AsyncExitStack) -> None:
    channel_id, (client,) = await channel_with_clients(name="idk")
    await exit_stack.enter_async_context(client)
    channel = await client.get_chat(get_channel_id(channel_id))

    assert channel.title == "idk"

    async with client.expect_updates_m(UpdateChannel):
        assert await channel.set_title("new title")
    channel2 = await client.get_chat(channel.id)
    assert channel2.title == "new title"


@pytest.mark.asyncio
async def test_change_channel_photo(
        channel_with_clients: ChannelWithClientsFactory, exit_stack: AsyncExitStack,
) -> None:
    channel_id, (client,) = await channel_with_clients()
    await exit_stack.enter_async_context(client)
    channel = await client.get_chat(get_channel_id(channel_id))

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
async def test_get_channel_participants_only_owner(
        channel_with_clients: ChannelWithClientsFactory, exit_stack: AsyncExitStack,
) -> None:
    channel_id, (client,) = await channel_with_clients()
    await exit_stack.enter_async_context(client)
    channel = await client.get_chat(get_channel_id(channel_id))

    participants: list[ChatMember] = [participant async for participant in client.get_chat_members(channel.id)]
    assert len(participants) == 1
    assert participants[0].user.id == client.me.id


@pytest.mark.asyncio
async def test_channel_and_promote_user(
        channel_with_clients: ChannelWithClientsFactory, exit_stack: AsyncExitStack,
) -> None:
    channel_id, (client1, client2,) = await channel_with_clients(2)
    await exit_stack.enter_async_context(client1)
    await exit_stack.enter_async_context(client2)
    channel = await client1.get_chat(get_channel_id(channel_id))

    user2 = await client1.resolve_user(client2)

    assert await client1.send_message(channel.id, "test message")
    await client1.expect_update(UpdateNewChannelMessage)
    await client2.expect_update(UpdateNewChannelMessage)

    with pytest.raises(Forbidden):
        assert await client2.send_message(channel.id, "test message 2")

    await client1.promote_chat_member(channel.id, user2.id, ChatPrivileges(can_post_messages=True))

    assert await client2.send_message(channel.id, "test message 2")
    await client1.expect_update(UpdateNewChannelMessage)
    await client2.expect_update(UpdateNewChannelMessage)


@pytest.mark.asyncio
async def test_channel_add_user(
        channel_with_clients: ChannelWithClientsFactory, client_with_auth: ClientFactory, exit_stack: AsyncExitStack,
) -> None:
    channel_id, (client1,) = await channel_with_clients(1)
    client2 = await client_with_auth()
    await exit_stack.enter_async_context(client1)
    await exit_stack.enter_async_context(client2)
    channel = await client1.get_chat(get_channel_id(channel_id))

    user2 = await client1.resolve_user(client2)
    user1 = await client2.resolve_user(client1)

    await client2.set_privacy(
        InputPrivacyKeyChatInvite(),
        InputPrivacyValueAllowUsers(users=[await client2.resolve_peer(user1.id)]),
    )

    assert await client1.get_chat_members_count(channel.id) == 1

    assert await client1.add_chat_members(channel.id, user2.id)
    await client2.expect_update(UpdateChannel)
    channel2 = await client2.get_chat(channel.id)
    assert channel2.id == channel.id

    assert await client1.get_chat_members_count(channel.id) == 2


@pytest.mark.asyncio
async def test_change_channel_username(
        channel_with_clients: ChannelWithClientsFactory, exit_stack: AsyncExitStack,
) -> None:
    channel_id, (client,) = await channel_with_clients()
    await exit_stack.enter_async_context(client)
    channel = await client.get_chat(get_channel_id(channel_id))

    assert channel.username is None

    assert await client.set_chat_username(channel.id, "test_channel")
    await client.expect_update(UpdateChannel)
    channel = await client.get_chat(channel.id)
    assert channel.username == "test_channel"


@pytest.mark.asyncio
async def test_change_channel_username_to_occupied_by_user(
        channel_with_clients: ChannelWithClientsFactory, exit_stack: AsyncExitStack,
) -> None:
    channel_id, (client,) = await channel_with_clients()
    await exit_stack.enter_async_context(client)
    channel = await client.get_chat(get_channel_id(channel_id))

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
        channel_with_clients: ChannelWithClientsFactory, exit_stack: AsyncExitStack, password_set: str | None,
        password_check: str, before: tuple[bool, bool], after: tuple[bool, bool], expect_updates_after: bool,
        expected_exception: type[Exception] | None,
) -> None:
    channel_id, (client1, client2,) = await channel_with_clients(2)
    await exit_stack.enter_async_context(client1)
    await exit_stack.enter_async_context(client2)

    user2 = await client1.resolve_user(client2)

    channel1 = await client1.get_chat(get_channel_id(channel_id))
    assert channel1.is_creator is before[0]

    channel2 = await client2.get_chat(get_channel_id(channel_id))
    assert channel2.is_creator is before[1]

    input_password = InputCheckPasswordEmpty()
    if password_set is not None:
        await client1.enable_cloud_password(password=password_set)
        input_password = compute_password_check(await client1.invoke(GetPassword()), password_check)

    request = EditCreator(
        channel=await client1.resolve_peer(get_channel_id(channel_id)),
        user_id=await client1.resolve_peer(user2.id),
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

    channel1 = await client1.get_chat(get_channel_id(channel_id))
    assert channel1.is_creator is after[0]

    channel2 = await client2.get_chat(get_channel_id(channel_id))
    assert channel2.is_creator is after[1]


@pytest.mark.asyncio
async def test_edit_channel_owner_fail_not_owner(
        channel_with_clients: ChannelWithClientsFactory, exit_stack: AsyncExitStack,
) -> None:
    channel_id, (client1, client2, client3,) = await channel_with_clients(3)
    await exit_stack.enter_async_context(client1)
    await exit_stack.enter_async_context(client2)
    await exit_stack.enter_async_context(client3)

    channel1 = await client1.get_chat(get_channel_id(channel_id))
    assert channel1.is_creator
    channel2 = await client2.get_chat(get_channel_id(channel_id))
    assert not channel2.is_creator
    channel3 = await client3.get_chat(get_channel_id(channel_id))
    assert not channel3.is_creator

    await client2.enable_cloud_password(password="test_passw0rd")

    user23 = await client2.resolve_user(client3)

    with pytest.raises(ChatAdminRequired):
        await client2.invoke(EditCreator(
            channel=await client2.resolve_peer(get_channel_id(channel_id)),
            user_id=await client2.resolve_peer(user23.id),
            password=compute_password_check(await client2.invoke(GetPassword()), "test_passw0rd"),
        ))

    channel1 = await client1.get_chat(get_channel_id(channel_id))
    assert channel1.is_creator
    channel2 = await client2.get_chat(get_channel_id(channel_id))
    assert not channel2.is_creator
    channel3 = await client3.get_chat(get_channel_id(channel_id))
    assert not channel3.is_creator


@pytest.mark.asyncio
async def test_edit_channel_owner_fail_invalid_user(
        channel_with_clients: ChannelWithClientsFactory, exit_stack: AsyncExitStack,
) -> None:
    channel_id, (client,) = await channel_with_clients(1)
    await exit_stack.enter_async_context(client)
    channel = await client.get_chat(get_channel_id(channel_id))

    assert channel.is_creator

    await client.enable_cloud_password(password="test_passw0rd")

    with pytest.raises(PeerIdInvalid):
        await client.invoke(EditCreator(
            channel=await client.resolve_peer(channel.id),
            user_id=InputUser(user_id=client.me.id + 1, access_hash=123456789),
            password=compute_password_check(await client.invoke(GetPassword()), "test_passw0rd"),
        ))

    channel1 = await client.get_chat(channel.id)
    assert channel1.is_creator


@pytest.mark.asyncio
async def test_edit_channel_owner_fail_user_not_participant(
        channel_with_clients: ChannelWithClientsFactory, client_with_auth: ClientFactory, exit_stack: AsyncExitStack,
) -> None:
    channel_id, (client1,) = await channel_with_clients(1)
    client2 = await client_with_auth()
    await exit_stack.enter_async_context(client1)
    await exit_stack.enter_async_context(client2)

    user2 = await client1.resolve_user(client2)

    channel1 = await client1.get_chat(get_channel_id(channel_id))
    assert channel1.is_creator

    await client1.enable_cloud_password(password="test_passw0rd")

    with pytest.raises(UserIdInvalid):
        await client1.invoke(EditCreator(
            channel=await client1.resolve_peer(get_channel_id(channel_id)),
            user_id=await client1.resolve_peer(user2.id),
            password=compute_password_check(await client1.invoke(GetPassword()), "test_passw0rd"),
        ))

    channel1 = await client1.get_chat(get_channel_id(channel_id))
    assert channel1.is_creator


@pytest.mark.asyncio
async def test_edit_channel_owner_fail_not_user(
        channel_with_clients: ChannelWithClientsFactory, exit_stack: AsyncExitStack,
) -> None:
    channel_id, (client,) = await channel_with_clients(1)
    await exit_stack.enter_async_context(client)
    channel = await client.get_chat(get_channel_id(channel_id))

    assert channel.is_creator

    await client.enable_cloud_password(password="test_passw0rd")

    with pytest.raises(UserIdInvalid):
        await client.invoke(EditCreator(
            channel=await client.resolve_peer(channel.id),
            user_id=await client.resolve_peer(channel.id),
            password=compute_password_check(await client.invoke(GetPassword()), "test_passw0rd"),
        ))

    channel1 = await client.get_chat(channel.id)
    assert channel1.is_creator


@pytest.mark.asyncio
async def test_delete_channel_success(
        channel_with_clients: ChannelWithClientsFactory, exit_stack: AsyncExitStack,
) -> None:
    channel_id, (client1, client2,) = await channel_with_clients(2)
    await exit_stack.enter_async_context(client1)
    await exit_stack.enter_async_context(client2)
    channel = await client1.get_chat(get_channel_id(channel_id))

    assert await client1.delete_channel(channel.id)
    await client1.expect_update(UpdateChannel)
    await client2.expect_update(UpdateChannel)

    with pytest.raises(ChannelPrivate):
        await client1.get_chat(channel.id)

    with pytest.raises(ChannelPrivate):
        await client2.get_chat(channel.id)


@pytest.mark.asyncio
async def test_delete_channel_fail_not_owner(
        channel_with_clients: ChannelWithClientsFactory, exit_stack: AsyncExitStack,
) -> None:
    channel_id, (client1, client2,) = await channel_with_clients(2)
    await exit_stack.enter_async_context(client1)
    await exit_stack.enter_async_context(client2)
    channel = await client1.get_chat(get_channel_id(channel_id))

    assert await client1.get_chat(channel.id)
    assert await client2.get_chat(channel.id)

    with pytest.raises(ChatAdminRequired):
        await client2.delete_channel(channel.id)

    assert await client1.get_chat(channel.id)
    assert await client2.get_chat(channel.id)


@pytest.mark.asyncio
async def test_channel_join(
        channel_with_clients: ChannelWithClientsFactory, client_with_auth: ClientFactory, exit_stack: AsyncExitStack,
        faker: Faker,
) -> None:
    channel_id, (client1,) = await channel_with_clients(1)
    client2 = await client_with_auth()
    await exit_stack.enter_async_context(client1)
    await exit_stack.enter_async_context(client2)

    channel = await client1.get_chat(get_channel_id(channel_id))
    await client1.send_message(channel.id, "test")

    channel_username = faker.user_name()

    async with client1.expect_updates_m(UpdateChannel):
        await client1.set_chat_username(channel.id, channel_username)

    assert await client1.get_chat_members_count(channel.id) == 1
    assert len([dialog async for dialog in client2.get_dialogs()]) == 0

    async with client2.expect_updates_m(UpdateChannel):
        channel2 = await client2.join_chat(channel_username)
    assert channel2

    assert channel.id == channel2.id

    assert await client1.get_chat_members_count(channel.id) == 2
    assert len([dialog async for dialog in client2.get_dialogs()]) == 1


@pytest.mark.asyncio
async def test_get_public_channel_messages_without_join(
        channel_with_clients: ChannelWithClientsFactory, client_with_auth: ClientFactory, exit_stack: AsyncExitStack,
        faker: Faker,
) -> None:
    channel_id, (client1,) = await channel_with_clients(1, create_service_message=True)
    client2 = await client_with_auth()
    await exit_stack.enter_async_context(client1)
    await exit_stack.enter_async_context(client2)
    channel = await client1.get_chat(get_channel_id(channel_id))

    channel_username = faker.user_name()

    async with client1.expect_updates_m(UpdateChannel):
        await client1.set_chat_username(channel.id, channel_username)

    messages = [m async for m in client2.get_chat_history(channel_username)]
    assert len(messages) == 1
    assert messages[0].service
    assert await client2.get_chat_history_count(channel_username) == 1

    message = await client1.send_message(channel_username, "test 123")

    messages = [m async for m in client2.get_chat_history(channel_username)]
    assert len(messages) == 2
    messages.sort(key=lambda msg: msg.id)
    assert messages[1].id == message.id
    assert messages[1].text == message.text
    assert messages[1].service is None


@pytest.mark.asyncio
async def test_channel_join_leave(
        channel_with_clients: ChannelWithClientsFactory, client_with_auth: ClientFactory, exit_stack: AsyncExitStack,
        faker: Faker,
) -> None:
    channel_id, (client1,) = await channel_with_clients(1, create_service_message=True)
    client2 = await client_with_auth()
    await exit_stack.enter_async_context(client1)
    await exit_stack.enter_async_context(client2)
    channel = await client1.get_chat(get_channel_id(channel_id))
    channel_username = faker.user_name()

    async with client1.expect_updates_m(UpdateChannel):
        await client1.set_chat_username(channel.id, channel_username)

    assert await client1.get_chat_members_count(channel.id) == 1
    assert len([dialog async for dialog in client2.get_dialogs()]) == 0

    async with client2.expect_updates_m(UpdateChannel):
        await client2.join_chat(channel_username)

    assert await client1.get_chat_members_count(channel.id) == 2
    assert len([dialog async for dialog in client2.get_dialogs()]) == 1

    async with client2.expect_updates_m(UpdateChannel):
        await client2.leave_chat(channel_username)

    assert await client1.get_chat_members_count(channel.id) == 1
    assert len([dialog async for dialog in client2.get_dialogs()]) == 0


@pytest.mark.asyncio
async def test_channel_supergroup_ban_user(
        channel_with_clients: ChannelWithClientsFactory, client_with_auth: ClientFactory, exit_stack: AsyncExitStack,
) -> None:
    channel_id, (client1,) = await channel_with_clients(1, supergroup=True, create_service_message=True)
    client2 = await client_with_auth()
    await exit_stack.enter_async_context(client1)
    await exit_stack.enter_async_context(client2)
    channel = await client1.get_chat(get_channel_id(channel_id))

    user2 = await client1.resolve_user(client2)

    invite_link = await channel.export_invite_link()
    await client2.join_chat(invite_link)
    await client2.expect_update(UpdateChannel)

    await client1.ban_chat_member(channel.id, user2.id)
    await client2.expect_update(UpdateChannel)

    with pytest.raises(ChannelPrivate):
        await client2.get_chat(channel.id)

    with pytest.raises(InviteHashExpired):
        await client2.join_chat(invite_link)


@pytest.mark.asyncio
async def test_channel_supergroup_ban_user_before_join(
        channel_with_clients: ChannelWithClientsFactory, client_with_auth: ClientFactory, exit_stack: AsyncExitStack,
) -> None:
    channel_id, (client1,) = await channel_with_clients(1, supergroup=True, create_service_message=True)
    client2 = await client_with_auth()
    await exit_stack.enter_async_context(client1)
    await exit_stack.enter_async_context(client2)
    channel = await client1.get_chat(get_channel_id(channel_id))

    user2 = await client1.resolve_user(client2)

    await client1.ban_chat_member(channel.id, user2.id)

    invite_link = await channel.export_invite_link()

    with pytest.raises(InviteHashExpired):
        await client2.join_chat(invite_link)


@pytest.mark.asyncio
async def test_channel_supergroup_unban_user(
        channel_with_clients: ChannelWithClientsFactory, client_with_auth: ClientFactory, exit_stack: AsyncExitStack,
) -> None:
    channel_id, (client1,) = await channel_with_clients(1, supergroup=True, create_service_message=True)
    client2 = await client_with_auth()
    await exit_stack.enter_async_context(client1)
    await exit_stack.enter_async_context(client2)
    channel = await client1.get_chat(get_channel_id(channel_id))

    user2 = await client1.resolve_user(client2)

    invite_link = await channel.export_invite_link()
    await client2.join_chat(invite_link)
    await client2.expect_update(UpdateChannel)

    await client1.ban_chat_member(channel.id, user2.id)
    await client2.expect_update(UpdateChannel)

    with pytest.raises(InviteHashExpired):
        await client2.join_chat(invite_link)

    await client1.unban_chat_member(channel.id, user2.id)

    await client2.join_chat(invite_link)


@pytest.mark.asyncio
async def test_change_channel_username_to_same(
        channel_with_clients: ChannelWithClientsFactory, exit_stack: AsyncExitStack
) -> None:
    channel_id, (client,) = await channel_with_clients()
    await exit_stack.enter_async_context(client)
    channel = await client.get_chat(get_channel_id(channel_id))

    assert channel.username is None

    assert await client.set_chat_username(channel.id, "test_channel")
    await client.expect_update(UpdateChannel)
    channel = await client.get_chat(channel.id)
    assert channel.username == "test_channel"

    with pytest.raises(UsernameNotModified):
        assert await client.set_chat_username(channel.id, "test_channel")


@pytest.mark.asyncio
async def test_change_channel_username_to_empty(
        channel_with_clients: ChannelWithClientsFactory, exit_stack: AsyncExitStack,
) -> None:
    channel_id, (client,) = await channel_with_clients()
    await exit_stack.enter_async_context(client)
    channel = await client.get_chat(get_channel_id(channel_id))

    assert channel.username is None

    assert await client.set_chat_username(channel.id, "test_channel")
    await client.expect_update(UpdateChannel)
    channel = await client.get_chat(channel.id)
    assert channel.username == "test_channel"

    assert await client.set_chat_username(channel.id, None)
    await client.expect_update(UpdateChannel)
    channel = await client.get_chat(channel.id)
    assert channel.username is None


@pytest.mark.asyncio
async def test_change_channel_username_to_empty_from_empty(
        channel_with_clients: ChannelWithClientsFactory, exit_stack: AsyncExitStack,
) -> None:
    channel_id, (client,) = await channel_with_clients()
    await exit_stack.enter_async_context(client)
    channel = await client.get_chat(get_channel_id(channel_id))

    assert channel.username is None

    with pytest.raises(UsernameNotModified):
        assert await client.set_chat_username(channel.id, None)


@pytest.mark.asyncio
async def test_change_channel_username_to_different_one(
        channel_with_clients: ChannelWithClientsFactory, exit_stack: AsyncExitStack,
) -> None:
    channel_id, (client,) = await channel_with_clients()
    await exit_stack.enter_async_context(client)
    channel = await client.get_chat(get_channel_id(channel_id))

    assert channel.username is None

    for username in ("test_channel", "test_channel1"):
        assert await client.set_chat_username(channel.id, username)
        await client.expect_update(UpdateChannel)
        channel = await client.get_chat(channel.id)
        assert channel.username == username


@pytest.mark.asyncio
async def test_channel_trigger_pyrogram_getchannels(
        channel_with_clients: ChannelWithClientsFactory, exit_stack: AsyncExitStack,
) -> None:
    channel_id, (client,) = await channel_with_clients()
    await exit_stack.enter_async_context(client)
    channel = await client.get_chat(get_channel_id(channel_id))

    another_client: TestClient = await exit_stack.enter_async_context(TestClient(phone_number="123456789"))
    peer = await another_client.resolve_peer(channel.id)
    assert isinstance(peer, InputPeerChannel)


@pytest.mark.parametrize(
    ("for_me", "after_start_idx_me", "after_start_idx_other",),
    [
        (True, 5, 0,),
        (False, 5, 5,),
    ],
    ids=("for me", "for everyone",),
)
@pytest.mark.asyncio
async def test_supergroup_delete_history(
        channel_with_clients: ChannelWithClientsFactory, exit_stack: AsyncExitStack,
        for_me: bool, after_start_idx_me: int, after_start_idx_other: int,
) -> None:
    channel_id, (client1, client2,) = await channel_with_clients(2, supergroup=True)
    await exit_stack.enter_async_context(client1)
    await exit_stack.enter_async_context(client2)
    group = await client1.get_chat(get_channel_id(channel_id))

    messages = [
        await client1.send_message(group.id, f"test {num}")
        for num in range(10)
    ]
    message_ids = [message.id for message in messages]

    await client1.invoke(DeleteHistory(
        for_everyone=not for_me,
        channel=await client1.resolve_peer(group.id),
        max_id=message_ids[5],
    ))

    after_message_ids_1 = [message.id async for message in client1.get_chat_history(group.id, 10)][::-1]
    after_message_ids_2 = [message.id async for message in client2.get_chat_history(group.id, 10)][::-1]

    assert after_message_ids_1 == message_ids[after_start_idx_me:]
    assert after_message_ids_2 == message_ids[after_start_idx_other:]


@pytest.mark.asyncio
async def test_supergroup_delete_participant_history(
        channel_with_clients: ChannelWithClientsFactory, exit_stack: AsyncExitStack,
) -> None:
    channel_id, (client1, client2,) = await channel_with_clients(2, supergroup=True)
    await exit_stack.enter_async_context(client1)
    await exit_stack.enter_async_context(client2)
    group = await client1.get_chat(get_channel_id(channel_id))

    user2 = await client1.resolve_user(client2)

    for i in range(20):
        if i % 2:
            await client1.send_message(group.id, f"test {i}")
        else:
            await client2.send_message(group.id, f"test {i}")

    await client1.delete_user_history(group.id, user2.id)

    after_messages = [
        (message.from_user.id, message.id)
        async for message in client1.get_chat_history(group.id, 10)
    ]

    assert all(author_id == client1.me.id for author_id, _ in after_messages)
    assert len(after_messages) == 10


# TODO: add tests for restricting chat members (including restricting before join)
