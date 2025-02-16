import pytest
from pyrogram.errors import InviteHashInvalid, UserAlreadyParticipant, PeerIdInvalid, InviteHashExpired, \
    InviteRequestSent
from pyrogram.raw.functions.messages import ExportChatInvite
from pyrogram.types import Chat, ChatPreview

from tests.conftest import TestClient

PHOTO_COLOR = (0x00, 0xff, 0x00)

"""
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


@pytest.mark.asyncio
async def test_get_exported_chat_invite_info() -> None:
    async with TestClient(phone_number="123456789") as client:
        group = await client.create_group("idk", [])
        invite_link = await group.export_invite_link()

        invite_info = await client.get_chat_invite_link(group.id, invite_link)
        assert invite_info
        assert not invite_info.is_revoked

        with pytest.raises(InviteHashExpired):
            await client.get_chat_invite_link(group.id, invite_link + "A")
        with pytest.raises(InviteHashExpired):
            await client.get_chat_invite_link(group.id, "invalid link")


@pytest.mark.asyncio
async def test_get_exported_chat_invites() -> None:
    async with TestClient(phone_number="123456789") as client:
        group = await client.create_group("idk", [])
        await group.export_invite_link()

        active_links = [link async for link in client.get_chat_admin_invite_links(group.id, "me", False)]
        revoked_links = [link async for link in client.get_chat_admin_invite_links(group.id, "me", True)]
        assert len(active_links) == 1
        assert len(revoked_links) == 0
        assert await client.get_chat_admin_invite_links_count(group.id, "me", False) == 1
        assert await client.get_chat_admin_invite_links_count(group.id, "me", True) == 0

        await group.export_invite_link()
        await group.export_invite_link()

        active_links = [link async for link in client.get_chat_admin_invite_links(group.id, "me", False)]
        revoked_links = [link async for link in client.get_chat_admin_invite_links(group.id, "me", True)]
        assert len(active_links) == 1
        assert len(revoked_links) == 2
        assert await client.get_chat_admin_invite_links_count(group.id, "me", False) == 1
        assert await client.get_chat_admin_invite_links_count(group.id, "me", True) == 2


@pytest.mark.asyncio
async def test_delete_revoked_exported_chat_invites() -> None:
    async with TestClient(phone_number="123456789") as client:
        group = await client.create_group("idk", [])
        await group.export_invite_link()

        assert await client.get_chat_admin_invite_links_count(group.id, "me", False) == 1
        assert await client.get_chat_admin_invite_links_count(group.id, "me", True) == 0

        await group.export_invite_link()
        await group.export_invite_link()

        assert await client.get_chat_admin_invite_links_count(group.id, "me", False) == 1
        assert await client.get_chat_admin_invite_links_count(group.id, "me", True) == 2

        await client.delete_chat_admin_invite_links(group.id, "me")

        assert await client.get_chat_admin_invite_links_count(group.id, "me", False) == 1
        assert await client.get_chat_admin_invite_links_count(group.id, "me", True) == 0


@pytest.mark.asyncio
async def test_get_chat_importers() -> None:
    async with TestClient(phone_number="123456789") as client1, TestClient(phone_number="1234567890") as client2:
        group = await client1.create_group("idk", [])
        invite_link = await group.export_invite_link()
        assert invite_link.startswith("https://t.me/+")

        assert [imp async for imp in client1.get_chat_invite_link_joiners(group.id, invite_link)] == []
        assert await client1.get_chat_invite_link_joiners_count(group.id, invite_link) == 0

        await client2.join_chat(invite_link)

        importers = [imp async for imp in client1.get_chat_invite_link_joiners(group.id, invite_link)]
        assert await client1.get_chat_invite_link_joiners_count(group.id, invite_link) == 1
        assert len(importers) == 1
        assert importers[0].user.id == client2.me.id
        assert not importers[0].pending
"""

@pytest.mark.asyncio
async def test_send_multiple_requests_on_same_invite() -> None:
    async with TestClient(phone_number="123456789") as client1, TestClient(phone_number="1234567890") as client2:
        group = await client1.create_group("idk", [])
        r = await client1.invoke(
            ExportChatInvite(
                peer=await client1.resolve_peer(group.id),
                legacy_revoke_permanent=True,
                request_needed=True,
            )
        )
        invite_link = r.link

        assert [req async for req in client1.get_chat_join_requests(group.id)] == []

        for _ in range(10):
            with pytest.raises(InviteRequestSent):
                await client2.join_chat(invite_link)

        assert len([req async for req in client1.get_chat_join_requests(group.id)]) == 1
        joiner_id = [req async for req in client1.get_chat_join_requests(group.id)][0].user.id
        assert joiner_id == client2.me.id


@pytest.mark.asyncio
async def test_request_approve_invite() -> None:
    async with TestClient(phone_number="123456789") as client1, TestClient(phone_number="1234567890") as client2:
        group = await client1.create_group("idk", [])
        r = await client1.invoke(
            ExportChatInvite(
                peer=await client1.resolve_peer(group.id),
                legacy_revoke_permanent=True,
                request_needed=True,
            )
        )
        invite_link = r.link

        assert [req async for req in client1.get_chat_join_requests(group.id)] == []

        with pytest.raises(InviteRequestSent):
            await client2.join_chat(invite_link)

        assert len([req async for req in client1.get_chat_join_requests(group.id)]) == 1
        joiner_id = [req async for req in client1.get_chat_join_requests(group.id)][0].user.id
        assert joiner_id == client2.me.id

        with pytest.raises(PeerIdInvalid):
            await client2.send_message(group.id, "test message")

        assert await client1.approve_chat_join_request(group.id, joiner_id)
        assert await client2.send_message(group.id, "test message")


@pytest.mark.asyncio
async def test_request_dismiss_invite() -> None:
    async with TestClient(phone_number="123456789") as client1, TestClient(phone_number="1234567890") as client2:
        group = await client1.create_group("idk", [])
        r = await client1.invoke(
            ExportChatInvite(
                peer=await client1.resolve_peer(group.id),
                legacy_revoke_permanent=True,
                request_needed=True,
            )
        )
        invite_link = r.link

        assert [req async for req in client1.get_chat_join_requests(group.id)] == []

        with pytest.raises(InviteRequestSent):
            await client2.join_chat(invite_link)

        assert len([req async for req in client1.get_chat_join_requests(group.id)]) == 1
        joiner_id = [req async for req in client1.get_chat_join_requests(group.id)][0].user.id
        assert joiner_id == client2.me.id

        with pytest.raises(PeerIdInvalid):
            await client2.send_message(group.id, "test message")

        assert await client1.decline_chat_join_request(group.id, joiner_id)

        assert [req async for req in client1.get_chat_join_requests(group.id)] == []
        with pytest.raises(PeerIdInvalid):
            assert await client2.send_message(group.id, "test message")
