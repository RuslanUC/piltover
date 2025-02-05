from datetime import datetime, UTC
from urllib.parse import urlparse

from tortoise.expressions import Q

from piltover.app.handlers.messages.sending import send_message_internal
from piltover.app.utils.updates_manager import UpdatesManager
from piltover.db.enums import PeerType, MessageType
from piltover.db.models import User, Peer, ChatParticipant, ChatInvite
from piltover.exceptions import ErrorRpc
from piltover.tl import InputUser, InputUserSelf, Updates, Long, ChatInviteAlready, ChatInvite as TLChatInvite, \
    ChatInviteExported
from piltover.tl.functions.messages import GetExportedChatInvites, GetAdminsWithInvites, GetChatInviteImporters, \
    ImportChatInvite, CheckChatInvite, ExportChatInvite, GetExportedChatInvite, DeleteRevokedExportedChatInvites
from piltover.tl.types.messages import ExportedChatInvites, ChatAdminsWithInvites, ChatInviteImporters, \
    ExportedChatInvite
from piltover.worker import MessageHandler

handler = MessageHandler("messages.invites")


@handler.on_request(GetExportedChatInvites)
async def get_exported_chat_invites(request: GetExportedChatInvites, user: User) -> ExportedChatInvites:
    peer = await Peer.from_input_peer_raise(user, request.peer)
    if peer.type is not PeerType.CHAT:
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    participant = await ChatParticipant.get_or_none(chat=peer.chat, user=user)
    if participant is None or not (participant.is_admin or peer.chat.creator_id == user.id):
        raise ErrorRpc(error_code=400, error_message="CHAT_ADMIN_REQUIRED")

    query = Q(chat=peer.chat, revoked=request.revoked)
    if isinstance(request.admin_id, (InputUser, InputUserSelf)):  # TODO: ??
        admin_peer = await Peer.from_input_peer_raise(user, request.admin_id, "ADMIN_ID_INVALID")
        query &= Q(user=admin_peer.peer_user(user))

    if request.offset_date:
        query &= Q(updated_at__lt=datetime.fromtimestamp(request.offset_date, UTC))

    limit = max(min(100, request.limit), 1)
    invites = []
    users = {}
    for chat_invite in await ChatInvite.filter(query).order_by("-updated_at").limit(limit):
        invites.append(chat_invite.to_tl())
        await chat_invite.tl_users_chats(user, users)

    return ExportedChatInvites(
        count=await ChatInvite.filter(query).count(),
        invites=invites,
        users=list(users.values()),
    )


@handler.on_request(ExportChatInvite)
async def export_chat_invite(request: ExportChatInvite, user: User) -> ChatInviteExported:
    peer = await Peer.from_input_peer_raise(user, request.peer)
    if peer.type is not PeerType.CHAT:
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    participant = await ChatParticipant.get_or_none(chat=peer.chat, user=user)
    if participant is None or not (participant.is_admin or peer.chat.creator_id == user.id):
        raise ErrorRpc(error_code=400, error_message="CHAT_ADMIN_REQUIRED")

    if request.legacy_revoke_permanent:
        await ChatInvite.filter(user=user, chat=peer.chat, revoked=False).update(revoked=True)

    invite = await ChatInvite.create(
        chat=peer.chat,
        user=user,
        request_needed=request.request_needed,
        usage_limit=request.usage_limit if not request.request_needed else None,
        title=request.title,
        expires_at=None if request.expire_date is None else datetime.fromtimestamp(request.expire_date, UTC),
    )

    return invite.to_tl()


@handler.on_request(GetAdminsWithInvites)
async def get_admins_with_invites(request: GetAdminsWithInvites, user: User) -> ChatAdminsWithInvites:
    peer = await Peer.from_input_peer_raise(user, request.peer)
    if peer.type is not PeerType.CHAT:
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    participant = await ChatParticipant.get_or_none(chat=peer.chat, user=user)
    if participant is None or not (participant.is_admin or peer.chat.creator_id == user.id):
        raise ErrorRpc(error_code=400, error_message="CHAT_ADMIN_REQUIRED")

    # TODO: get admins with invites

    return ChatAdminsWithInvites(
        admins=[],
        users=[],
    )


@handler.on_request(GetChatInviteImporters)
async def get_chat_invite_importers(request: GetChatInviteImporters, user: User) -> ChatInviteImporters:
    peer = await Peer.from_input_peer_raise(user, request.peer)
    if peer.type is not PeerType.CHAT:
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    participant = await ChatParticipant.get_or_none(chat=peer.chat, user=user)
    if participant is None or not (participant.is_admin or peer.chat.creator_id == user.id):
        raise ErrorRpc(error_code=400, error_message="CHAT_ADMIN_REQUIRED")

    # TODO: get users who joined chat with provided invite

    return ChatInviteImporters(
        count=0,
        importers=[],
        users=[],
    )


async def _get_invite_with_some_checks(invite_hash: str) -> ChatInvite:
    if not invite_hash:
        raise ErrorRpc(error_code=400, error_message="INVITE_HASH_EMPTY")
    query = ChatInvite.query_from_link_hash(invite_hash.strip()) & Q(revoked=False)
    invite = await ChatInvite.get_or_none(query).select_related("chat")
    if invite is None:
        raise ErrorRpc(error_code=400, error_message="INVITE_HASH_INVALID")
    if invite.usage_limit is not None and invite.usage > invite.usage_limit:
        raise ErrorRpc(error_code=400, error_message="USERS_TOO_MUCH")
    if invite.expires_at is not None and datetime.now(UTC) > invite.expires_at:
        raise ErrorRpc(error_code=400, error_message="INVITE_HASH_EXPIRED")

    return invite


def _get_invite_hash_from_link(invite_link: str) -> str | None:
    if "t.me/+" in invite_link:
        return invite_link.rpartition("t.me/+")[2] or None
    if "t.me/joinchat/" in invite_link:
        return invite_link.rpartition("t.me/joinchat/")[2] or None
    if invite_link.startswith("tg://"):
        url = urlparse(invite_link)
        query = dict(kv.split("=", maxsplit=1) for kv in url.query.split("&"))
        return query.get("invite") or None


@handler.on_request(ImportChatInvite)
async def import_chat_invite(request: ImportChatInvite, user: User) -> Updates:
    invite = await _get_invite_with_some_checks(request.hash)
    if await ChatParticipant.filter(user=user, chat=invite.chat).exists():
        raise ErrorRpc(error_code=400, error_message="USER_ALREADY_PARTICIPANT")

    chat_peers = {peer.owner.id: peer for peer in await Peer.filter(chat=invite.chat).select_related("owner")}
    chat_peers[user.id] = await Peer.create(owner=user, chat=invite.chat, type=PeerType.CHAT)
    await ChatParticipant.create(user=user, chat=invite.chat, inviter_id=invite.user_id, )

    updates = await UpdatesManager.create_chat(user, invite.chat, list(chat_peers.values()))

    updates_msg = await send_message_internal(
        user, chat_peers[user.id], None, None, False,
        author=user, type=MessageType.SERVICE_CHAT_USER_INVITE_JOIN,
        extra_info=Long.write(invite.user_id),
    )

    updates.updates.extend(updates_msg.updates)

    return updates


@handler.on_request(CheckChatInvite)
async def check_chat_invite(request: CheckChatInvite, user: User) -> TLChatInvite | ChatInviteAlready:
    invite = await _get_invite_with_some_checks(request.hash)
    if await ChatParticipant.filter(user=user, chat=invite.chat).exists():
        return ChatInviteAlready(chat=await invite.chat.to_tl(user))

    return TLChatInvite(
        request_needed=invite.request_needed,
        title=invite.chat.name,
        about=invite.chat.description,
        photo=await invite.chat.to_tl_photo(user),
        participants_count=1,  # TODO: fetch members count
        color=1,
    )


@handler.on_request(GetExportedChatInvite)
async def get_exported_chat_invite(request: GetExportedChatInvite, user: User) -> ExportedChatInvite:
    peer = await Peer.from_input_peer_raise(user, request.peer)
    if peer.type is not PeerType.CHAT:
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    participant = await ChatParticipant.get_or_none(chat=peer.chat, user=user)
    if participant is None or not (participant.is_admin or peer.chat.creator_id == user.id):
        raise ErrorRpc(error_code=400, error_message="CHAT_ADMIN_REQUIRED")

    if (invite_hash := _get_invite_hash_from_link(request.link)) is None:
        raise ErrorRpc(error_code=400, error_message="INVITE_HASH_EXPIRED")

    query = (
            ChatInvite.query_from_link_hash(invite_hash)
            & Q(chat=peer.chat)
            & (Q(expires_at__isnull=True) | Q(expires_at__isnull=False, expires_at__gt=datetime.now(UTC)))
    )
    invite = await ChatInvite.get_or_none(query)
    if invite is None:
        raise ErrorRpc(error_code=400, error_message="INVITE_HASH_EXPIRED")

    users, _ = await invite.tl_users_chats(user, {})

    return ExportedChatInvite(
        invite=invite.to_tl(),
        users=list(users.values()),
    )


@handler.on_request(DeleteRevokedExportedChatInvites)
async def delete_revoked_exported_chat_invites(request: DeleteRevokedExportedChatInvites, user: User) -> bool:
    peer = await Peer.from_input_peer_raise(user, request.peer)
    if peer.type is not PeerType.CHAT:
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    participant = await ChatParticipant.get_or_none(chat=peer.chat, user=user)
    if participant is None or not (participant.is_admin or peer.chat.creator_id == user.id):
        raise ErrorRpc(error_code=400, error_message="CHAT_ADMIN_REQUIRED")

    query = Q(chat=peer.chat, revoked=True)
    if isinstance(request.admin_id, (InputUser, InputUserSelf)):
        admin_peer = await Peer.from_input_peer_raise(user, request.admin_id, "ADMIN_ID_INVALID")
        query &= Q(user=admin_peer.peer_user(user))

    await ChatInvite.filter(query).delete()
    return True