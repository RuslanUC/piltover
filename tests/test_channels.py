from io import BytesIO
from typing import cast

import pytest
from PIL import Image
from pyrogram.errors import ChatWriteForbidden
from pyrogram.types import ChatMember, ChatPrivileges

from tests.conftest import TestClient, color_is_near

PHOTO_COLOR = (0x00, 0xff, 0x80)


@pytest.mark.asyncio
async def test_create_channel() -> None:
    async with TestClient(phone_number="123456789") as client:
        channel = await client.create_channel("idk")
        assert channel.title == "idk"


@pytest.mark.asyncio
async def test_edit_channel_title() -> None:
    async with TestClient(phone_number="123456789") as client:
        channel = await client.create_channel("idk")
        assert channel.title == "idk"

        assert await channel.set_title("new title")
        channel2 = await client.get_chat(channel.id)
        assert channel2.title == "new title"


@pytest.mark.asyncio
async def test_change_channel_photo() -> None:
    async with TestClient(phone_number="123456789") as client:
        channel = await client.create_channel("idk")
        assert channel.photo is None

        photo = Image.new(mode="RGB", size=(256, 256), color=PHOTO_COLOR)
        photo_file = BytesIO()
        setattr(photo_file, "name", "photo.png")
        photo.save(photo_file, format="PNG")

        await client.set_chat_photo(channel.id, photo=photo_file)
        channel = await client.get_chat(channel.id)
        assert channel.photo is not None

        downloaded_photo_file = await client.download_media(channel.photo.big_file_id, in_memory=True)
        downloaded_photo_file.seek(0)
        downloaded_photo = Image.open(downloaded_photo_file)
        assert color_is_near(PHOTO_COLOR, cast(tuple[int, int, int], downloaded_photo.getpixel((0, 0))))


@pytest.mark.asyncio
async def test_get_channel_participants_only_owner() -> None:
    async with TestClient(phone_number="123456789") as client:
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
        user1 = await client2.get_users("test1_username")
        user2 = await client1.get_users("test2_username")

        channel = await client1.create_channel("idk")
        assert channel

        invite_link = await channel.export_invite_link()
        await client2.join_chat(invite_link)

        assert await client1.send_message(channel.id, "test message")

        with pytest.raises(ChatWriteForbidden):
            assert await client2.send_message(channel.id, "test message 2")

        await client1.promote_chat_member(channel.id, user2.id, ChatPrivileges(can_post_messages=True))

        assert await client2.send_message(channel.id, "test message 2")


@pytest.mark.asyncio
async def test_channel_add_user() -> None:
    async with TestClient(phone_number="123456789") as client1, TestClient(phone_number="1234567890") as client2:
        await client1.set_username("test1_username")
        await client2.set_username("test2_username")

        channel = await client1.create_channel("idk")
        assert channel

        assert await client1.get_chat_members_count(channel.id) == 1

        assert await client1.add_chat_members(channel.id, "test2_username")
        channel2 = await client2.get_chat(channel.id)
        assert channel2.id == channel.id

        assert await client1.get_chat_members_count(channel.id) == 2
