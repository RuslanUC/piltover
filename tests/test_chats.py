from contextlib import AsyncExitStack
from io import BytesIO
from typing import cast

import pytest
from PIL import Image
from pyrogram.errors import PeerIdInvalid, ChatAdminRequired, ChatWriteForbidden
from pyrogram.raw.functions.messages import EditChatAdmin, GetDialogs, MigrateChat
from pyrogram.raw.types import UpdateUserName, UpdateNewMessage, MessageService, MessageActionChatMigrateTo, \
    UpdateNewChannelMessage
from pyrogram.raw.types.messages import Dialogs
from pyrogram.utils import get_channel_id

from piltover.tl import InputPeerEmpty
from tests.client import TestClient
from tests.utils import color_is_near

PHOTO_COLOR = (0x00, 0xff, 0x00)


@pytest.mark.asyncio
async def test_change_chat_title() -> None:
    async with TestClient(phone_number="123456789") as client:
        group = await client.create_group("idk", [])
        assert group.title == "idk"

        await client.set_chat_title(group.id, "test 123")
        group = await client.get_chat(group.id)
        assert group.title == "test 123"


@pytest.mark.asyncio
async def test_change_chat_description() -> None:
    async with TestClient(phone_number="123456789") as client:
        group = await client.create_group("idk", [])
        assert group.description is None

        await client.set_chat_description(group.id, "test description")
        group = await client.get_chat(group.id)
        assert group.description == "test description"


@pytest.mark.asyncio
async def test_change_chat_photo() -> None:
    async with TestClient(phone_number="123456789") as client:
        group = await client.create_group("idk", [])
        assert group.photo is None

        photo = Image.new(mode="RGB", size=(256, 256), color=PHOTO_COLOR)
        photo_file = BytesIO()
        setattr(photo_file, "name", "photo.png")
        photo.save(photo_file, format="PNG")

        await client.set_chat_photo(group.id, photo=photo_file)
        group = await client.get_chat(group.id)
        assert group.photo is not None

        downloaded_photo_file = await client.download_media(group.photo.big_file_id, in_memory=True)
        downloaded_photo_file.seek(0)
        downloaded_photo = Image.open(downloaded_photo_file)
        assert color_is_near(PHOTO_COLOR, cast(tuple[int, int, int], downloaded_photo.getpixel((0, 0))))


@pytest.mark.asyncio
async def test_create_group_chat_with_another_user() -> None:
    async with TestClient(phone_number="123456789") as client1, TestClient(phone_number="1234567890") as client2:
        await client1.set_username("test1_username")
        await client2.set_username("test2_username")
        user1 = await client2.get_users("test1_username")
        user2 = await client1.get_users("test2_username")

        assert len([dialog async for dialog in client1.get_dialogs()]) == 0
        assert len([dialog async for dialog in client2.get_dialogs()]) == 0

        group = await client1.create_group("idk 1", [])
        assert len([dialog async for dialog in client1.get_dialogs()]) == 1
        assert len([dialog async for dialog in client2.get_dialogs()]) == 0

        group2 = await client1.create_group("idk 2", [user2.id])
        assert len([dialog async for dialog in client1.get_dialogs()]) == 2
        assert len([dialog async for dialog in client2.get_dialogs()]) == 1


@pytest.mark.asyncio
async def test_add_delete_user_in_group_chat() -> None:
    async with TestClient(phone_number="123456789") as client1, TestClient(phone_number="1234567890") as client2:
        await client1.set_username("test1_username")
        await client2.set_username("test2_username")
        user1 = await client2.get_users("test1_username")
        user2 = await client1.get_users("test2_username")

        assert len([dialog async for dialog in client1.get_dialogs()]) == 0
        assert len([dialog async for dialog in client2.get_dialogs()]) == 0

        group = await client1.create_group("idk 1", [])
        assert len([dialog async for dialog in client1.get_dialogs()]) == 1
        assert len([dialog async for dialog in client2.get_dialogs()]) == 0
        assert await client1.get_chat_members_count(group.id) == 1
        with pytest.raises(PeerIdInvalid):
            await client2.send_message(group.id, "test1")

        await client1.add_chat_members(group.id, [user2.id])
        assert len([dialog async for dialog in client1.get_dialogs()]) == 1
        assert len([dialog async for dialog in client2.get_dialogs()]) == 1
        assert await client1.get_chat_members_count(group.id) == 2
        await client2.send_message(group.id, "test2")

        await client1.ban_chat_member(group.id, user2.id)
        assert len([dialog async for dialog in client1.get_dialogs()]) == 1
        assert len([dialog async for dialog in client2.get_dialogs()]) == 1
        assert await client1.get_chat_members_count(group.id) == 1
        with pytest.raises(ChatWriteForbidden):
            await client2.send_message(group.id, "test3")


@pytest.mark.asyncio
async def test_promote_user_to_admin() -> None:
    async with TestClient(phone_number="123456789") as client1, TestClient(phone_number="1234567890") as client2:
        await client1.set_username("test1_username")
        await client2.set_username("test2_username")
        user1 = await client2.get_users("test1_username")
        user2 = await client1.get_users("test2_username")

        group = await client1.create_group("idk", [user2.id])
        with pytest.raises(ChatAdminRequired):
            await client2.set_chat_title(group.id, "test 123")

        assert await client1.invoke(EditChatAdmin(
            chat_id=abs(group.id),
            user_id=await client1.resolve_peer(user2.id),
            is_admin=True,
        ))

        assert await client2.set_chat_title(group.id, "test 123")

        assert await client1.invoke(EditChatAdmin(
            chat_id=abs(group.id),
            user_id=await client1.resolve_peer(user2.id),
            is_admin=False,
        ))

        with pytest.raises(ChatAdminRequired):
            await client2.set_chat_title(group.id, "test 123")


@pytest.mark.asyncio
async def test_archive_unarchive_dialog() -> None:
    async with TestClient(phone_number="123456789") as client:
        group = await client.create_group("idk", [])
        assert group.photo is None

        dialogs: Dialogs = await client.invoke(
            GetDialogs(offset_date=0, offset_id=0, offset_peer=InputPeerEmpty(), limit=10, hash=0, folder_id=0),
        )
        assert len(dialogs.dialogs) == 1
        dialogs: Dialogs = await client.invoke(
            GetDialogs(offset_date=0, offset_id=0, offset_peer=InputPeerEmpty(), limit=10, hash=0, folder_id=1),
        )
        assert len(dialogs.dialogs) == 0

        await group.archive()

        dialogs: Dialogs = await client.invoke(
            GetDialogs(offset_date=0, offset_id=0, offset_peer=InputPeerEmpty(), limit=10, hash=0, folder_id=0),
        )
        assert len(dialogs.dialogs) == 0
        dialogs: Dialogs = await client.invoke(
            GetDialogs(offset_date=0, offset_id=0, offset_peer=InputPeerEmpty(), limit=10, hash=0, folder_id=1),
        )
        assert len(dialogs.dialogs) == 1

        await group.unarchive()

        dialogs: Dialogs = await client.invoke(
            GetDialogs(offset_date=0, offset_id=0, offset_peer=InputPeerEmpty(), limit=10, hash=0, folder_id=0),
        )
        assert len(dialogs.dialogs) == 1
        dialogs: Dialogs = await client.invoke(
            GetDialogs(offset_date=0, offset_id=0, offset_peer=InputPeerEmpty(), limit=10, hash=0, folder_id=1),
        )
        assert len(dialogs.dialogs) == 0


@pytest.mark.asyncio
async def test_migrate_basic_chat_to_supergroup(exit_stack: AsyncExitStack) -> None:
    client1: TestClient = await exit_stack.enter_async_context(TestClient(phone_number="123456789"))
    client2: TestClient = await exit_stack.enter_async_context(TestClient(phone_number="123456780"))

    await client2.set_username("test2_username")
    await client2.expect_update(UpdateUserName)

    async with client1.expect_updates_m(UpdateNewMessage), client2.expect_updates_m(UpdateNewMessage):
        group = await client1.create_group("idk basic group", ["test2_username"])
    assert group

    async with client1.expect_updates_m(UpdateNewMessage), client2.expect_updates_m(UpdateNewMessage):
        assert await client1.send_message(group.id, "test message 1")
    async with client1.expect_updates_m(UpdateNewMessage), client2.expect_updates_m(UpdateNewMessage):
        assert await client2.send_message(group.id, "test message 2")

    assert await client1.invoke(MigrateChat(chat_id=-group.id))
    upd1 = await client1.expect_update(UpdateNewMessage)
    upd2 = await client2.expect_update(UpdateNewMessage)
    assert isinstance(upd1.message, MessageService)
    assert isinstance(upd2.message, MessageService)
    assert isinstance(upd1.message.action, MessageActionChatMigrateTo)
    channel_id = upd1.message.action.channel_id

    channel1 = await client1.get_chat(get_channel_id(channel_id))
    channel2 = await client2.get_chat(get_channel_id(channel_id))
    assert channel1
    assert channel2

    with pytest.raises(PeerIdInvalid):
        await client1.send_message(group.id, "test message 3")
    with pytest.raises(PeerIdInvalid):
        await client2.send_message(group.id, "test message 4")

    async with client1.expect_updates_m(UpdateNewChannelMessage), client2.expect_updates_m(UpdateNewChannelMessage):
        assert await client1.send_message(channel1.id, "test message 5")
    async with client1.expect_updates_m(UpdateNewChannelMessage), client2.expect_updates_m(UpdateNewChannelMessage):
        assert await client2.send_message(channel1.id, "test message 6")

    dialogs1 = [dialog async for dialog in client1.get_dialogs()]
    dialogs2 = [dialog async for dialog in client2.get_dialogs()]

    assert len(dialogs1) == 1
    assert len(dialogs2) == 1
