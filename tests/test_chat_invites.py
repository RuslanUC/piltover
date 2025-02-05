import pytest
from pyrogram.errors import InviteHashInvalid, UserAlreadyParticipant, PeerIdInvalid
from pyrogram.types import Chat, ChatPreview

from tests.conftest import TestClient

PHOTO_COLOR = (0x00, 0xff, 0x00)


@pytest.mark.asyncio
async def test_export_chat_invite() -> None:
    async with TestClient(phone_number="123456789") as client:
        group = await client.create_group("idk", [])
        invite_link = await group.export_invite_link()

        assert invite_link.startswith("https://t.me/+")


@pytest.mark.asyncio
async def test_get_chat_invite_info() -> None:
    async with TestClient(phone_number="123456789") as client1, TestClient(phone_number="1234567890") as client2:
        group = await client1.create_group("idk", [])
        invite_link = await group.export_invite_link()
        assert invite_link.startswith("https://t.me/+")

        chat1 = await client1.get_chat(invite_link)
        assert chat1
        assert isinstance(chat1, Chat)
        assert chat1.id == group.id
        assert chat1.is_creator
        assert chat1.title == group.title

        chat2 = await client2.get_chat(invite_link)
        assert chat2
        assert isinstance(chat2, ChatPreview)
        assert chat2.title == group.title
        
        
@pytest.mark.asyncio
async def test_get_chat_invite_info_after_exporting_new_link_with_revoking_existing() -> None:
    async with TestClient(phone_number="123456789") as client1:
        group = await client1.create_group("idk", [])
        
        invite_link1 = await group.export_invite_link()
        chat = await client1.get_chat(invite_link1)
        assert chat
        assert isinstance(chat, Chat)
        assert chat.id == group.id
        assert chat.is_creator
        assert chat.title == group.title

        invite_link2 = await group.export_invite_link()
        with pytest.raises(InviteHashInvalid):
            await client1.get_chat(invite_link1)

        chat = await client1.get_chat(invite_link2)
        assert chat
        assert isinstance(chat, Chat)
        assert chat.id == group.id
        assert chat.is_creator
        assert chat.title == group.title
        

@pytest.mark.asyncio
async def test_join_chat_invite() -> None:
    async with TestClient(phone_number="123456789") as client1, TestClient(phone_number="1234567890") as client2:
        group = await client1.create_group("idk", [])
        invite_link = await group.export_invite_link()
        assert invite_link.startswith("https://t.me/+")

        with pytest.raises(UserAlreadyParticipant):
            await client1.join_chat(invite_link)

        with pytest.raises(PeerIdInvalid):
            await client2.send_message(group.id, "test message")

        chat2 = await client2.join_chat(invite_link)
        assert chat2.id == group.id
        assert await client2.send_message(chat2.id, "test message")
