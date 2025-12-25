from datetime import datetime, UTC
from typing import cast
from urllib.parse import urlparse

from tortoise.expressions import Q, Subquery
from tortoise.functions import Count
from tortoise.transactions import in_transaction

import piltover.app.utils.updates_manager as upd
from piltover.app.handlers.messages.sending import send_message_internal
from piltover.app.utils.updates_manager import UpdatesWithDefaults
from piltover.app_config import AppConfig
from piltover.db.enums import PeerType, MessageType, ChatBannedRights, ChatAdminRights, AdminLogEntryAction
from piltover.db.models import User, Peer, ChatParticipant, ChatInvite, ChatInviteRequest, Chat, ChatBase, Channel, \
    Dialog, Message, AdminLogEntry
from piltover.enums import ReqHandlerFlags
from piltover.exceptions import ErrorRpc
from piltover.session_manager import SessionManager
from piltover.tl import InputUser, InputUserSelf, Updates, ChatInviteAlready, ChatInvite as TLChatInvite, \
    ChatInviteExported, ChatInviteImporter, InputPeerUser, InputPeerUserFromMessage, MessageActionChatJoinedByLink, \
    MessageActionChatJoinedByRequest, MessageActionChatAddUser, ChatAdminWithInvites, UpdatePendingJoinRequests
from piltover.tl.functions.messages import GetExportedChatInvites, GetAdminsWithInvites, GetChatInviteImporters, \
    ImportChatInvite, CheckChatInvite, ExportChatInvite, GetExportedChatInvite, DeleteRevokedExportedChatInvites, \
    HideChatJoinRequest, HideAllChatJoinRequests, ExportChatInvite_133, ExportChatInvite_134, EditExportedChatInvite
from piltover.tl.types.messages import ExportedChatInvites, ChatAdminsWithInvites, ChatInviteImporters, \
    ExportedChatInvite
from piltover.utils.users_chats_channels import UsersChatsChannels
from piltover.worker import MessageHandler

handler = MessageHandler("messages.invites")


@handler.on_request(GetExportedChatInvites, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def get_exported_chat_invites(request: GetExportedChatInvites, user: User) -> ExportedChatInvites:
    peer = await Peer.from_input_peer_raise(user, request.peer, allow_migrated_chat=True)
    if peer.type not in (PeerType.CHAT, PeerType.CHANNEL):
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    participant = await ChatParticipant.get_or_none(Chat.query(peer.chat_or_channel) & Q(user=user))
    if participant is None or not (participant.is_admin or peer.chat_or_channel.creator_id == user.id):
        raise ErrorRpc(error_code=400, error_message="CHAT_ADMIN_REQUIRED")

    query = Chat.query(peer.chat_or_channel) & Q(revoked=request.revoked)
    if isinstance(request.admin_id, (InputUser, InputUserSelf)):
        admin_peer = await Peer.from_input_peer_raise(user, request.admin_id, "ADMIN_ID_INVALID")
        query &= Q(user=admin_peer.peer_user(user))

    if request.offset_date:
        query &= Q(updated_at__lt=datetime.fromtimestamp(request.offset_date, UTC))

    limit = max(min(100, request.limit), 1)
    invites = []
    ucc = UsersChatsChannels()
    for chat_invite in await ChatInvite.filter(query).order_by("-updated_at").limit(limit):
        invites.append(await chat_invite.to_tl())
        ucc.add_chat_invite(chat_invite)

    users, *_ = await ucc.resolve(user, fetch_chats=False, fetch_channels=False)

    return ExportedChatInvites(
        count=await ChatInvite.filter(query).count(),
        invites=invites,
        users=users,
    )


@handler.on_request(ExportChatInvite_133)
@handler.on_request(ExportChatInvite_134)
@handler.on_request(ExportChatInvite)
async def export_chat_invite(request: ExportChatInvite, user: User) -> ChatInviteExported:
    peer = await Peer.from_input_peer_raise(user, request.peer)
    if peer.type not in (PeerType.CHAT, PeerType.CHANNEL):
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    participant = await ChatParticipant.get_or_none(Chat.query(peer.chat_or_channel) & Q(user=user))
    if isinstance(peer.chat_or_channel, Chat) \
            and not peer.chat.user_has_permission(participant, ChatBannedRights.INVITE_USERS):
        raise ErrorRpc(error_code=400, error_message="CHAT_ADMIN_REQUIRED")
    elif isinstance(peer.chat_or_channel, Channel) \
            and not peer.channel.admin_has_permission(participant, ChatAdminRights.INVITE_USERS):
        raise ErrorRpc(error_code=400, error_message="CHAT_ADMIN_REQUIRED")

    if request.legacy_revoke_permanent:
        await ChatInvite.filter(
            Chat.query(peer.chat_or_channel) & Q(user=user, revoked=False)
        ).update(revoked=True)

    request_new = isinstance(request, (ExportChatInvite_134, ExportChatInvite))
    request_needed = request.request_needed if request_new else False
    title = request.title if request_new else None
    expires_at = None if request.expire_date is None else datetime.fromtimestamp(request.expire_date, UTC)

    invite = await ChatInvite.create(
        **Chat.or_channel(peer.chat_or_channel),
        user=user,
        request_needed=request_needed,
        usage_limit=request.usage_limit if not request_needed else None,
        title=title,
        expires_at=expires_at,
    )

    return await invite.to_tl()


@handler.on_request(GetAdminsWithInvites, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def get_admins_with_invites(request: GetAdminsWithInvites, user: User) -> ChatAdminsWithInvites:
    peer = await Peer.from_input_peer_raise(user, request.peer)
    if peer.type not in (PeerType.CHAT, PeerType.CHANNEL):
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    participant = await ChatParticipant.get_or_none(Chat.query(peer.chat_or_channel) & Q(user=user))
    if not peer.chat_or_channel.admin_has_permission(participant, ChatAdminRights.INVITE_USERS):
        raise ErrorRpc(error_code=400, error_message="CHAT_ADMIN_REQUIRED")

    invites = await ChatInvite.filter(
        **Chat.or_channel(peer.chat_or_channel),
        user__id__in=Subquery(
            ChatParticipant.filter(
                **Chat.or_channel(peer.chat_or_channel), admin_rights__gt=0,
            ).values_list("user__id", flat=True)
        )
    ).select_related("user")

    admins_tl = {}
    users_to_tl = {}

    for invite in invites:
        user_id = invite.user.id
        users_to_tl[user_id] = invite.user
        if user_id not in admins_tl:
            admins_tl[user_id] = ChatAdminWithInvites(admin_id=user_id, invites_count=0, revoked_invites_count=0)
        admins_tl[user_id].invites_count += 1
        if invite.revoked:
            admins_tl[user_id].revoked_invites_count += 1

    return ChatAdminsWithInvites(
        admins=list(admins_tl.values()),
        users=await User.to_tl_bulk(users_to_tl.values(), user),
    )


@handler.on_request(GetChatInviteImporters, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def get_chat_invite_importers(request: GetChatInviteImporters, user: User) -> ChatInviteImporters:
    peer = await Peer.from_input_peer_raise(user, request.peer, allow_migrated_chat=True)
    if peer.type not in (PeerType.CHAT, PeerType.CHANNEL):
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    participant = await ChatParticipant.get_or_none(Chat.query(peer.chat_or_channel) & Q(user=user))
    if not peer.chat_or_channel.admin_has_permission(participant, ChatAdminRights.INVITE_USERS):
        raise ErrorRpc(error_code=400, error_message="CHAT_ADMIN_REQUIRED")

    importers = []
    users_to_tl = []

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
            users_to_tl.append(request.user)

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
            users_to_tl.append(importer.user)

        count = await ChatParticipant.filter(query_no_date).count()

    return ChatInviteImporters(
        count=count,
        importers=importers,
        users=await User.to_tl_bulk(users_to_tl, user),
    )


async def _get_invite_with_some_checks(invite_hash: str) -> ChatInvite:
    if not invite_hash:
        raise ErrorRpc(error_code=400, error_message="INVITE_HASH_EMPTY")
    query = ChatInvite.query_from_link_hash(invite_hash.strip()) & Q(revoked=False)
    invite = await ChatInvite.get_or_none(query).select_related("chat", "channel")
    if invite is None:
        raise ErrorRpc(error_code=400, error_message="INVITE_HASH_INVALID")
    if invite.usage_limit is not None and invite.usage > invite.usage_limit:
        raise ErrorRpc(error_code=400, error_message="USERS_TOO_MUCH")
    if (invite.expires_at is not None and datetime.now(UTC) > invite.expires_at) \
            or (invite.chat is not None and invite.chat.migrated):
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


async def user_join_chat_or_channel(chat_or_channel: ChatBase, user: User, from_invite: ChatInvite | None) -> Updates:
    if isinstance(chat_or_channel, Channel) \
            and await ChatParticipant.filter(user=user, channel__id__not=None).count() > AppConfig.CHANNELS_PER_USER_LIMIT:
        raise ErrorRpc(error_code=400, error_message="CHANNELS_TOO_MUCH")

    member_limit = AppConfig.BASIC_GROUP_MEMBER_LIMIT
    if isinstance(chat_or_channel, Channel):
        member_limit = AppConfig.SUPER_GROUP_MEMBER_LIMIT  # TODO: add separate limit for channels
    if await ChatParticipant.filter(**Chat.or_channel(chat_or_channel)).count() > member_limit:
        raise ErrorRpc(error_code=400, error_message="USERS_TOO_MUCH")

    min_message_id = None
    if isinstance(chat_or_channel, Channel):
        if chat_or_channel.hidden_prehistory:
            min_message_id = cast(
                int | None,
                await Message.filter(
                    peer__owner=None, peer__channel=chat_or_channel,
                ).order_by("-id").first().values_list("id", flat=True)
            )
            min_message_id = (min_message_id + 1) if min_message_id is not None else None
        else:
            min_message_id = chat_or_channel.min_available_id

    async with in_transaction():
        new_peer, _ = await Peer.get_or_create(
            owner=user, type=PeerType.CHAT if isinstance(chat_or_channel, Chat) else PeerType.CHANNEL,
            **Chat.or_channel(chat_or_channel),
        )
        await ChatParticipant.create(
            user=user,
            inviter_id=from_invite.user_id if from_invite is not None else 0,
            invite=from_invite,
            min_message_id=min_message_id,
            **Chat.or_channel(chat_or_channel),
        )
        await ChatInviteRequest.filter(id__in=Subquery(
            ChatInviteRequest.filter(
                Chat.query(chat_or_channel, "invite") & Q(user=user)
            ).values_list("id", flat=True)
        )).delete()
        await Dialog.create_or_unhide(new_peer)
        if isinstance(chat_or_channel, Channel):
            await AdminLogEntry.create(
                channel=chat_or_channel,
                user=user,
                # TODO: PARTICIPANT_JOIN_INVITE / PARTICIPANT_JOIN_REQUEST
                action=AdminLogEntryAction.PARTICIPANT_JOIN,
            )

    if isinstance(chat_or_channel, Channel):
        channel = cast(Channel, chat_or_channel)
        await SessionManager.subscribe_to_channel(channel.id, [user.id])

        # TODO: send SERVICE_CHAT_USER_INVITE_JOIN or SERVICE_CHAT_USER_ADD message if channel is a supergroup
        return await upd.update_channel_for_user(channel, user)

    chat_peers = {
        peer.owner.id: peer
        for peer in await Peer.filter(Chat.query(chat_or_channel)).select_related("owner", "chat", "channel")
    }

    updates = await upd.create_chat(user, cast(Chat, chat_or_channel), list(chat_peers.values()))
    if from_invite is not None:
        updates_msg = await send_message_internal(
            user, chat_peers[user.id], None, None, False,
            author=user, type=MessageType.SERVICE_CHAT_USER_INVITE_JOIN,
            extra_info=MessageActionChatJoinedByLink(inviter_id=from_invite.user_id).write(),
        )
    else:
        updates_msg = await send_message_internal(
            user, chat_peers[user.id], None, None, False,
            author=user, type=MessageType.SERVICE_CHAT_USER_ADD,
            extra_info=MessageActionChatAddUser(users=[user.id]).write(),
        )

    updates.updates.extend(updates_msg.updates)

    return updates


@handler.on_request(ImportChatInvite, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def import_chat_invite(request: ImportChatInvite, user: User) -> Updates:
    invite = await _get_invite_with_some_checks(request.hash)
    if await ChatParticipant.filter(Chat.query(invite.chat_or_channel) & Q(user=user)).exists():
        raise ErrorRpc(error_code=400, error_message="USER_ALREADY_PARTICIPANT")
    if invite.request_needed or isinstance(invite.chat_or_channel, Channel) and invite.channel.join_request:
        query = Chat.query(invite.chat_or_channel, "invite") & Q(user=user)
        if not await ChatInviteRequest.filter(query).exists():
            # TODO: send updatePendingJoinRequests
            await ChatInviteRequest.create(user=user, invite=invite)
        raise ErrorRpc(error_code=400, error_message="INVITE_REQUEST_SENT")

    return await user_join_chat_or_channel(invite.chat_or_channel, user, invite)


@handler.on_request(CheckChatInvite, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def check_chat_invite(request: CheckChatInvite, user: User) -> TLChatInvite | ChatInviteAlready:
    invite = await _get_invite_with_some_checks(request.hash)
    if await ChatParticipant.filter(Chat.query(invite.chat_or_channel) & Q(user=user)).exists():
        return ChatInviteAlready(chat=await invite.chat_or_channel.to_tl(user))

    channel = invite.channel
    return TLChatInvite(
        channel=isinstance(invite.chat_or_channel, Channel),
        broadcast=not channel.supergroup if channel is not None else False,
        megagroup=channel.supergroup if channel is not None else False,
        request_needed=invite.request_needed or channel is not None and channel.join_request,
        title=invite.chat_or_channel.name,
        about=invite.chat_or_channel.description,
        photo=await invite.chat_or_channel.to_tl_photo(),
        participants_count=await ChatParticipant.filter(Chat.query(invite.chat_or_channel)).count(),
        color=1 if channel is None or channel.accent_color_id is None else channel.accent_color_id,
    )


@handler.on_request(GetExportedChatInvite, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def get_exported_chat_invite(request: GetExportedChatInvite, user: User) -> ExportedChatInvite:
    peer = await Peer.from_input_peer_raise(user, request.peer, allow_migrated_chat=True)
    if peer.type not in (PeerType.CHAT, PeerType.CHANNEL):
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    participant = await ChatParticipant.get_or_none(Chat.query(peer.chat_or_channel) & Q(user=user))
    if not peer.chat_or_channel.admin_has_permission(participant, ChatAdminRights.INVITE_USERS):
        raise ErrorRpc(error_code=400, error_message="CHAT_ADMIN_REQUIRED")

    if (invite_hash := _get_invite_hash_from_link(request.link)) is None:
        raise ErrorRpc(error_code=400, error_message="INVITE_HASH_EXPIRED")

    query = (
            ChatInvite.query_from_link_hash(invite_hash)
            & Chat.query(peer.chat_or_channel)
            & (Q(expires_at__isnull=True) | Q(expires_at__isnull=False, expires_at__gt=datetime.now(UTC)))
    )
    invite = await ChatInvite.get_or_none(query).select_related("user")
    if invite is None:
        raise ErrorRpc(error_code=400, error_message="INVITE_HASH_EXPIRED")

    return ExportedChatInvite(
        invite=await invite.to_tl(),
        users=[await invite.user.to_tl(user)],
    )


@handler.on_request(DeleteRevokedExportedChatInvites, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def delete_revoked_exported_chat_invites(request: DeleteRevokedExportedChatInvites, user: User) -> bool:
    peer = await Peer.from_input_peer_raise(user, request.peer)
    if peer.type not in (PeerType.CHAT, PeerType.CHANNEL):
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    participant = await ChatParticipant.get_or_none(Chat.query(peer.chat_or_channel) & Q(user=user))
    if not peer.chat_or_channel.admin_has_permission(participant, ChatAdminRights.INVITE_USERS):
        raise ErrorRpc(error_code=400, error_message="CHAT_ADMIN_REQUIRED")

    query = Chat.query(peer.chat_or_channel) & Q(revoked=True)
    if isinstance(request.admin_id, (InputUser, InputUserSelf)):
        admin_peer = await Peer.from_input_peer_raise(user, request.admin_id, "ADMIN_ID_INVALID")
        query &= Q(user=admin_peer.peer_user(user))

    await ChatInvite.filter(query).delete()
    return True


async def make_chat_join_request_updates(chat: ChatBase, user: User) -> Updates:
    pending = await ChatInviteRequest.filter(
        Chat.query(chat, "invite")
    ).annotate(total_count=Count("id")).order_by("-created_at").limit(25).values_list("id", "total_count")
    if pending:
        recent_users = [user_id for user_id, _ in pending]
        count = pending[0][1]
    else:
        recent_users = []
        count = 0

    # TODO: create peers
    users = []
    if recent_users:
        users = await User.to_tl_bulk(await User.filter(id__in=recent_users), user)

    return UpdatesWithDefaults(
        updates=[
            UpdatePendingJoinRequests(
                peer=chat.to_tl_peer(),
                requests_pending=count,
                recent_requesters=recent_users,
            ),
        ],
        users=users,
    )


async def add_requested_users_to_chat(user: User, chat: ChatBase, requests: list[ChatInviteRequest]) -> Updates:
    if not requests:
        return await make_chat_join_request_updates(chat, user)

    member_limit = AppConfig.BASIC_GROUP_MEMBER_LIMIT
    if isinstance(chat, Channel):
        member_limit = AppConfig.SUPER_GROUP_MEMBER_LIMIT  # TODO: add separate limit for channels
    if await ChatParticipant.filter(**Chat.or_channel(chat)).count() + len(requests) > member_limit:
        raise ErrorRpc(error_code=400, error_message="USERS_TOO_MUCH")

    peer_type = PeerType.CHAT if isinstance(chat, Chat) else PeerType.CHANNEL
    this_peer = await Peer.get_or_none(
        owner=user, type=peer_type, **Chat.or_channel(chat),
    ).select_related("owner", "chat", "channel")

    requested_users = [request.user.id for request in requests]
    new_peers = {
        peer.owner.id: peer
        for peer in await Peer.filter(
            owner__id__in=requested_users, type=peer_type, **Chat.or_channel(chat)
        ).select_related("owner")
    }
    participants_to_create = []
    for request in requests:
        if request.user.id not in new_peers:
            new_peers[request.user.id] = await Peer.create(
                owner=request.user, type=peer_type, **Chat.or_channel(chat)
            )
        participants_to_create.append(ChatParticipant(
            user=request.user, inviter_id=request.invite.user_id, invite=request.invite, **Chat.or_channel(chat)
        ))

    await ChatParticipant.bulk_create(participants_to_create, ignore_conflicts=True)
    await ChatInviteRequest.filter(id__in=Subquery(
        ChatInviteRequest.filter(
            Chat.query(chat, "invite") & Q(user__id__in=requested_users)
        ).values_list("id", flat=True)
    )).delete()

    if isinstance(chat, Chat):
        chat_peers = await Peer.filter(Chat.query(chat)).select_related("owner")
        await upd.create_chat(user, chat, chat_peers)
    else:
        # TODO: send SERVICE_CHAT_USER_INVITE_JOIN and SERVICE_CHAT_USER_REQUEST_JOIN
        await SessionManager.subscribe_to_channel(chat.id, requested_users)
        return await upd.update_channel_for_user(chat, user)

    for request in requests:
        await send_message_internal(
            user, this_peer, None, None, False,
            author=request.user, type=MessageType.SERVICE_CHAT_USER_INVITE_JOIN,
            extra_info=MessageActionChatJoinedByLink(inviter_id=request.invite.user_id).write(),
        )
        await send_message_internal(
            request.user, new_peers[request.user.id], None, None, False,
            opposite=False, author=request.user, type=MessageType.SERVICE_CHAT_USER_REQUEST_JOIN,
            extra_info=MessageActionChatJoinedByRequest().write()
        )

    return await make_chat_join_request_updates(chat, user)


@handler.on_request(HideChatJoinRequest)
async def hide_chat_join_request(request: HideChatJoinRequest, user: User) -> Updates:
    peer = await Peer.from_input_peer_raise(user, request.peer)
    if peer.type not in (PeerType.CHAT, PeerType.CHANNEL):
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    participant = await ChatParticipant.get_or_none(Chat.query(peer.chat_or_channel) & Q(user=user))
    if not peer.chat_or_channel.admin_has_permission(participant, ChatAdminRights.INVITE_USERS):
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
        return await make_chat_join_request_updates(peer.chat_or_channel, user)

    return await add_requested_users_to_chat(user, peer.chat_or_channel, [invite_request])


@handler.on_request(HideAllChatJoinRequests, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def hide_all_chat_join_requests(request: HideAllChatJoinRequests, user: User) -> Updates:
    peer = await Peer.from_input_peer_raise(user, request.peer)
    if peer.type not in (PeerType.CHAT, PeerType.CHANNEL):
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    participant = await ChatParticipant.get_or_none(Chat.query(peer.chat_or_channel) & Q(user=user))
    if not peer.chat_or_channel.admin_has_permission(participant, ChatAdminRights.INVITE_USERS):
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
        return await make_chat_join_request_updates(peer.chat_or_channel, user)

    return await add_requested_users_to_chat(user, peer.chat_or_channel, requests)


@handler.on_request(EditExportedChatInvite)
async def edit_exported_chat_invite(request: EditExportedChatInvite, user: User) -> ExportedChatInvite:
    peer = await Peer.from_input_peer_raise(user, request.peer, allow_migrated_chat=True)
    if peer.type not in (PeerType.CHAT, PeerType.CHANNEL):
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    participant = await ChatParticipant.get_or_none(Chat.query(peer.chat_or_channel) & Q(user=user))
    if not peer.chat_or_channel.admin_has_permission(participant, ChatAdminRights.INVITE_USERS):
        raise ErrorRpc(error_code=400, error_message="CHAT_ADMIN_REQUIRED")

    if (invite_hash := _get_invite_hash_from_link(request.link)) is None:
        raise ErrorRpc(error_code=400, error_message="INVITE_HASH_EXPIRED")
    invite = await ChatInvite.get_or_none(
        ChatInvite.query_from_link_hash(invite_hash.strip()) & Chat.query(peer.chat_or_channel) & Q(revoked=False)
    ).select_related("user")
    if invite is None:
        raise ErrorRpc(error_code=400, error_message="INVITE_HASH_EXPIRED")

    update_fields = []

    if request.revoked:
        invite.revoked = True
        update_fields.append("revoked")
    #if request.expire_date:
    #    if invite.expires_at is None or request.expire_date < (time() + 60):
    #        raise ErrorRpc(error_code=400, error_message="CHAT_INVITE_PERMANENT")
    #    invite.expires_at = datetime.fromtimestamp(request.expire_date, UTC)
    #    update_fields.append("expires_at")
    if request.title:
        invite.title = request.title
        update_fields.append("title")

    # TODO: usage_limit, expire_date, request_needed

    if update_fields:
        await invite.save(update_fields=update_fields)

    return ExportedChatInvite(
        invite=await invite.to_tl(),
        users=[await invite.user.to_tl(user)],
    )
