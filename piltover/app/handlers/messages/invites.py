from datetime import datetime, UTC

from tortoise.expressions import Q

from piltover.app.handlers.messages.sending import send_message_internal
from piltover.app.utils.updates_manager import UpdatesManager
from piltover.db.enums import PeerType, MessageType
from piltover.db.models import User, Peer, ChatParticipant, ChatInvite
from piltover.exceptions import ErrorRpc
from piltover.tl import InputUser, InputUserSelf, Updates, Long, ChatInviteAlready, ChatInvite as TLChatInvite, \
    ChatInviteExported
from piltover.tl.functions.messages import GetExportedChatInvites, GetAdminsWithInvites, GetChatInviteImporters, \
    ImportChatInvite, CheckChatInvite, ExportChatInvite
from piltover.tl.types.messages import ExportedChatInvites, ChatAdminsWithInvites, ChatInviteImporters
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
        count=len(invites),
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
        # TODO: request.expire_date
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
    if False:  # TODO: add invites expiration
        raise ErrorRpc(error_code=400, error_message="INVITE_HASH_EXPIRED")

    return invite


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
