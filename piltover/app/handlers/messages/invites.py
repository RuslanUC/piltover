from datetime import datetime, UTC
from time import time
from typing import cast
from urllib.parse import urlparse

from tortoise.expressions import Q, Subquery

from piltover.app.handlers.messages.sending import send_message_internal
from piltover.app.utils.updates_manager import UpdatesManager
from piltover.db.enums import PeerType, MessageType
from piltover.db.models import User, Peer, ChatParticipant, ChatInvite, ChatInviteRequest, Chat, ChatBase
from piltover.db.models._utils import resolve_users_chats
from piltover.exceptions import ErrorRpc
from piltover.tl import InputUser, InputUserSelf, Updates, ChatInviteAlready, ChatInvite as TLChatInvite, \
    ChatInviteExported, ChatInviteImporter, InputPeerUser, InputPeerUserFromMessage, MessageActionChatJoinedByLink, \
    MessageActionChatJoinedByRequest
from piltover.tl.functions.messages import GetExportedChatInvites, GetAdminsWithInvites, GetChatInviteImporters, \
    ImportChatInvite, CheckChatInvite, ExportChatInvite, GetExportedChatInvite, DeleteRevokedExportedChatInvites, \
    HideChatJoinRequest, HideAllChatJoinRequests
from piltover.tl.types.messages import ExportedChatInvites, ChatAdminsWithInvites, ChatInviteImporters, \
    ExportedChatInvite
from piltover.worker import MessageHandler

handler = MessageHandler("messages.invites")


@handler.on_request(GetExportedChatInvites)
async def get_exported_chat_invites(request: GetExportedChatInvites, user: User) -> ExportedChatInvites:
    peer = await Peer.from_input_peer_raise(user, request.peer)
    if peer.type is not PeerType.CHAT:
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    participant = await ChatParticipant.get_or_none(Chat.query(peer.chat_or_channel) & Q(user=user))
    if participant is None or not (participant.is_admin or peer.chat_or_channel.creator_id == user.id):
        raise ErrorRpc(error_code=400, error_message="CHAT_ADMIN_REQUIRED")

    query = Chat.query(peer.chat_or_channel) & Q(revoked=request.revoked)
    if isinstance(request.admin_id, (InputUser, InputUserSelf)):  # TODO: ??
        admin_peer = await Peer.from_input_peer_raise(user, request.admin_id, "ADMIN_ID_INVALID")
        query &= Q(user=admin_peer.peer_user(user))

    if request.offset_date:
        query &= Q(updated_at__lt=datetime.fromtimestamp(request.offset_date, UTC))

    limit = max(min(100, request.limit), 1)
    invites = []
    users_q = Q()
    for chat_invite in await ChatInvite.filter(query).order_by("-updated_at").limit(limit):
        invites.append(chat_invite.to_tl())
        users_q, *_ = chat_invite.query_users_chats(users_q)

    users, *_ = await resolve_users_chats(user, users_q, None, None, {}, None, None)

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

    participant = await ChatParticipant.get_or_none(Chat.query(peer.chat_or_channel) & Q(user=user))
    if participant is None or not (participant.is_admin or peer.chat_or_channel.creator_id == user.id):
        raise ErrorRpc(error_code=400, error_message="CHAT_ADMIN_REQUIRED")

    if request.legacy_revoke_permanent:
        await ChatInvite.filter(
            Chat.query(peer.chat_or_channel) & Q(user=user, revoked=False)
        ).update(revoked=True)

    invite = await ChatInvite.create(
        **Chat.or_channel(peer.chat_or_channel),
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

    participant = await ChatParticipant.get_or_none(Chat.query(peer.chat_or_channel) & Q(user=user))
    if participant is None or not (participant.is_admin or peer.chat_or_channel.creator_id == user.id):
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

    participant = await ChatParticipant.get_or_none(Chat.query(peer.chat_or_channel) & Q(user=user))
    if participant is None or not (participant.is_admin or peer.chat_or_channel.creator_id == user.id):
        raise ErrorRpc(error_code=400, error_message="CHAT_ADMIN_REQUIRED")

    importers = []
    users = []

    limit = max(min(100, request.limit), 1)
    invite: ChatInvite | None = None

    if request.link:
        if (invite_hash := _get_invite_hash_from_link(request.link)) is None:
            raise ErrorRpc(error_code=400, error_message="INVITE_HASH_EXPIRED")
        invite = await ChatInvite.get_or_none(
            ChatInvite.query_from_link_hash(invite_hash.strip()) & Chat.query(peer.chat_or_channel)
        )
        if invite is None:
            raise ErrorRpc(error_code=400, error_message="INVITE_HASH_EXPIRED")

    if request.requested:
        query_no_date = Chat.query(peer.chat_or_channel, "invite")
        if invite is not None:
            query_no_date &= Q(invite=invite)
        if request.offset_date:
            query = query_no_date & Q(created_at__lt=datetime.fromtimestamp(request.offset_date, UTC))
        else:
            query = query_no_date

        request: ChatInviteRequest
        async for request in ChatInviteRequest.filter(query).order_by("-created_at").limit(limit).select_related("user"):
            importers.append(ChatInviteImporter(
                requested=True,
                user_id=request.user.id,
                date=int(request.created_at.timestamp()),
            ))
            users.append(await request.user.to_tl(user))

        count = await ChatInviteRequest.filter(query_no_date).count()
    else:
        query_no_date = Chat.query(peer.chat_or_channel)
        if invite is not None:
            query_no_date &= Q(invite=invite)
        if request.offset_date:
            query = query_no_date & Q(invited_at__lt=datetime.fromtimestamp(request.offset_date, UTC))
        else:
            query = query_no_date

        importer: ChatParticipant
        async for importer in ChatParticipant.filter(query).order_by("-invited_at").limit(limit).select_related("user"):
            importers.append(ChatInviteImporter(
                requested=False,
                user_id=importer.user.id,
                date=int(importer.invited_at.timestamp()),
            ))
            users.append(await importer.user.to_tl(user))

        count = await ChatParticipant.filter(query_no_date).count()

    return ChatInviteImporters(
        count=count,
        importers=importers,
        users=users,
    )


async def _get_invite_with_some_checks(invite_hash: str) -> ChatInvite:
    if not invite_hash:
        raise ErrorRpc(error_code=400, error_message="INVITE_HASH_EMPTY")
    query = ChatInvite.query_from_link_hash(invite_hash.strip()) & Q(revoked=False)
    # TODO: add "channel" to select_related when channel model will be added
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
    if await ChatParticipant.filter(Chat.query(invite.chat_or_channel) & Q(user=user)).exists():
        raise ErrorRpc(error_code=400, error_message="USER_ALREADY_PARTICIPANT")
    if invite.request_needed:
        # TODO: check for requests for current invite or all invites?
        query = Chat.query(invite.chat_or_channel, "invite") & Q(user=user)
        if not await ChatInviteRequest.filter(query).exists():
            # TODO: send updatePendingJoinRequests
            await ChatInviteRequest.create(user=user, invite=invite)
        raise ErrorRpc(error_code=400, error_message="INVITE_REQUEST_SENT")

    chat_peers = {
        peer.owner.id: peer
        for peer in await Peer.filter(Chat.query(invite.chat_or_channel)).select_related("owner")
    }
    chat_peers[user.id] = await Peer.create(owner=user, type=PeerType.CHAT, **Chat.or_channel(invite.chat_or_channel))
    await ChatParticipant.create(user=user, inviter_id=invite.user_id, invite=invite, **Chat.or_channel(invite.chat_or_channel))
    await ChatInviteRequest.filter(id__in=Subquery(
        ChatInviteRequest.filter(
            Chat.query(invite.chat_or_channel, "invite") & Q(user=user)
        ).values_list("id", flat=True)
    )).delete()

    if isinstance(invite.chat_or_channel, Chat):
        updates = await UpdatesManager.create_chat(user, cast(Chat, invite.chat_or_channel), list(chat_peers.values()))
    else:
        raise NotImplementedError("TODO: send updates when user is added to channel")

    updates_msg = await send_message_internal(
        user, chat_peers[user.id], None, None, False,
        author=user, type=MessageType.SERVICE_CHAT_USER_INVITE_JOIN,
        extra_info=MessageActionChatJoinedByLink(inviter_id=invite.user_id).write(),
    )

    updates.updates.extend(updates_msg.updates)

    return updates


@handler.on_request(CheckChatInvite)
async def check_chat_invite(request: CheckChatInvite, user: User) -> TLChatInvite | ChatInviteAlready:
    invite = await _get_invite_with_some_checks(request.hash)
    if await ChatParticipant.filter(Chat.query(invite.chat_or_channel) & Q(user=user)).exists():
        return ChatInviteAlready(chat=await invite.chat_or_channel.to_tl(user))

    return TLChatInvite(
        request_needed=invite.request_needed,
        title=invite.chat_or_channel.name,
        about=invite.chat_or_channel.description,
        photo=await invite.chat_or_channel.to_tl_photo(user),
        participants_count=await ChatParticipant.filter(Chat.query(invite.chat_or_channel)).count(),
        color=1,
    )


@handler.on_request(GetExportedChatInvite)
async def get_exported_chat_invite(request: GetExportedChatInvite, user: User) -> ExportedChatInvite:
    peer = await Peer.from_input_peer_raise(user, request.peer)
    if peer.type is not PeerType.CHAT:
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    participant = await ChatParticipant.get_or_none(Chat.query(peer.chat_or_channel) & Q(user=user))
    if participant is None or not (participant.is_admin or peer.chat_or_channel.creator_id == user.id):
        raise ErrorRpc(error_code=400, error_message="CHAT_ADMIN_REQUIRED")

    if (invite_hash := _get_invite_hash_from_link(request.link)) is None:
        raise ErrorRpc(error_code=400, error_message="INVITE_HASH_EXPIRED")

    query = (
            ChatInvite.query_from_link_hash(invite_hash)
            & Chat.query(peer.chat_or_channel)
            & (Q(expires_at__isnull=True) | Q(expires_at__isnull=False, expires_at__gt=datetime.now(UTC)))
    )
    invite = await ChatInvite.get_or_none(query)
    if invite is None:
        raise ErrorRpc(error_code=400, error_message="INVITE_HASH_EXPIRED")

    users, *_ = await resolve_users_chats(user, *invite.query_users_chats(Q()), {}, None, None)

    return ExportedChatInvite(
        invite=invite.to_tl(),
        users=list(users.values()),
    )


@handler.on_request(DeleteRevokedExportedChatInvites)
async def delete_revoked_exported_chat_invites(request: DeleteRevokedExportedChatInvites, user: User) -> bool:
    peer = await Peer.from_input_peer_raise(user, request.peer)
    if peer.type is not PeerType.CHAT:
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    participant = await ChatParticipant.get_or_none(Chat.query(peer.chat_or_channel) & Q(user=user))
    if participant is None or not (participant.is_admin or peer.chat_or_channel.creator_id == user.id):
        raise ErrorRpc(error_code=400, error_message="CHAT_ADMIN_REQUIRED")

    query = Chat.query(peer.chat_or_channel) & Q(revoked=True)
    if isinstance(request.admin_id, (InputUser, InputUserSelf)):
        admin_peer = await Peer.from_input_peer_raise(user, request.admin_id, "ADMIN_ID_INVALID")
        query &= Q(user=admin_peer.peer_user(user))

    await ChatInvite.filter(query).delete()
    return True


async def add_requested_users_to_chat(user: User, chat: ChatBase, requests: list[ChatInviteRequest]) -> Updates:
    if not requests:
        return Updates(updates=[], users=[], chats=[], date=int(time()), seq=0)

    chat_peers = {
        peer.owner.id: peer
        for peer in await Peer.filter(Chat.query(chat)).select_related("owner")
    }
    participants = []
    for request in requests:
        if request.user.id not in chat_peers:
            # TODO: change type= to PeerType.CHANNEL when it will be added and chat type is Channel
            chat_peers[request.user.id] = await Peer.create(
                owner=request.user, type=PeerType.CHAT, **Chat.or_channel(chat)
            )
        participants.append(ChatParticipant(
            user=request.user, inviter_id=request.invite.user_id, invite=request.invite, **Chat.or_channel(chat)
        ))

    await ChatParticipant.bulk_create(participants)
    await ChatInviteRequest.filter(id__in=Subquery(
        ChatInviteRequest.filter(
            Chat.query(chat, "invite") & Q(user__id__in=list(chat_peers.keys()))
        ).values_list("id", flat=True)
    )).delete()

    if isinstance(chat, Chat):
        updates = await UpdatesManager.create_chat(user, chat, list(chat_peers.values()))
    else:
        raise NotImplementedError("TODO: send updates when user is added to channel")

    for request in requests:
        updates_msg = await send_message_internal(
            user, chat_peers[user.id], None, None, False,
            author=request.user, type=MessageType.SERVICE_CHAT_USER_INVITE_JOIN,
            extra_info=MessageActionChatJoinedByLink(inviter_id=request.invite.user_id).write(),
        )
        await send_message_internal(
            request.user, chat_peers[request.user.id], None, None, False,
            opposite=False, author=request.user, type=MessageType.SERVICE_CHAT_USER_REQUEST_JOIN,
            extra_info=MessageActionChatJoinedByRequest().write()
        )

        updates.updates.extend(updates_msg.updates)

    return updates


@handler.on_request(HideChatJoinRequest)
async def hide_chat_join_request(request: HideChatJoinRequest, user: User) -> Updates:
    peer = await Peer.from_input_peer_raise(user, request.peer)
    if peer.type is not PeerType.CHAT:
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    participant = await ChatParticipant.get_or_none(Chat.query(peer.chat_or_channel) & Q(user=user))
    if participant is None or not (participant.is_admin or peer.chat_or_channel.creator_id == user.id):
        raise ErrorRpc(error_code=400, error_message="CHAT_ADMIN_REQUIRED")

    if not isinstance(request.user_id, (InputPeerUser, InputPeerUserFromMessage)):
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    invite_request = await ChatInviteRequest.filter(
        Chat.query(peer.chat_or_channel, "invite") & Q(user__id=request.user_id.user_id)
    ).select_related("user", "invite").first()
    if invite_request is None:
        raise ErrorRpc(error_code=400, error_message="HIDE_REQUESTER_MISSING")

    if not request.approved:
        await ChatInviteRequest.filter(id__in=Subquery(
            ChatInviteRequest.filter(
                Chat.query(peer.chat_or_channel, "invite") & Q(user=invite_request.user)
            ).values_list("id", flat=True)
        )).delete()
        # TODO: what should be in updates.updates?
        return Updates(updates=[], users=[], chats=[], date=int(time()), seq=0)

    return await add_requested_users_to_chat(user, peer.chat_or_channel, [invite_request])


@handler.on_request(HideAllChatJoinRequests)
async def hide_all_chat_join_requests(request: HideAllChatJoinRequests, user: User) -> Updates:
    peer = await Peer.from_input_peer_raise(user, request.peer)
    if peer.type is not PeerType.CHAT:
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    participant = await ChatParticipant.get_or_none(Chat.query(peer.chat_or_channel) & Q(user=user))
    if participant is None or not (participant.is_admin or peer.chat_or_channel.creator_id == user.id):
        raise ErrorRpc(error_code=400, error_message="CHAT_ADMIN_REQUIRED")

    query = Chat.query(peer.chat_or_channel, "invite")

    if request.link:
        if (invite_hash := _get_invite_hash_from_link(request.link)) is None:
            raise ErrorRpc(error_code=400, error_message="INVITE_HASH_EXPIRED")
        invite = await ChatInvite.get_or_none(
            ChatInvite.query_from_link_hash(invite_hash.strip()) & Chat.query(peer.chat_or_channel)
        )
        if invite is None:
            raise ErrorRpc(error_code=400, error_message="INVITE_HASH_EXPIRED")
        query &= Q(invite=invite)

    requests = await ChatInviteRequest.filter(query)
    if not requests:
        raise ErrorRpc(error_code=400, error_message="HIDE_REQUESTER_MISSING")

    if not request.approved:
        await ChatInviteRequest.filter(id__in=Subquery(
            ChatInviteRequest.filter(query).values_list("id", flat=True)
        )).delete()
        # TODO: what should be in updates.updates?
        return Updates(updates=[], users=[], chats=[], date=int(time()), seq=0)

    return await add_requested_users_to_chat(user, peer.chat_or_channel, requests)
