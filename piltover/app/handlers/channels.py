from time import time
from typing import cast

from tortoise.expressions import Q, Subquery

import piltover.app.utils.updates_manager as upd
from piltover.app.handlers.messages.chats import resolve_input_chat_photo
from piltover.app.handlers.messages.history import format_messages_internal
from piltover.app.handlers.messages.sending import send_message_internal
from piltover.app.utils.utils import validate_username
from piltover.db.enums import MessageType, PeerType, ChatBannedRights, ChatAdminRights, PrivacyRuleKeyType
from piltover.db.models import User, Channel, Peer, Dialog, ChatParticipant, Message, ReadState, PrivacyRule, \
    ChatInviteRequest, Username
from piltover.enums import ReqHandlerFlags
from piltover.exceptions import ErrorRpc
from piltover.session_manager import SessionManager
from piltover.tl import MessageActionChannelCreate, UpdateChannel, Updates, InputChannelEmpty, ChatEmpty, \
    InputChannelFromMessage, InputChannel, ChannelFull, PhotoEmpty, PeerNotifySettings, MessageActionChatEditTitle, \
    Long, InputMessageID, InputMessageReplyTo, ChannelParticipantsRecent, ChannelParticipantsAdmins, \
    ChannelParticipantsSearch
from piltover.tl.functions.channels import GetChannelRecommendations, GetAdminedPublicChannels, CheckUsername, \
    CreateChannel, GetChannels, GetFullChannel, EditTitle, EditPhoto, GetMessages, DeleteMessages, EditBanned, \
    EditAdmin, GetParticipants, GetParticipant, ReadHistory, InviteToChannel, InviteToChannel_133, ToggleSignatures, \
    UpdateUsername, ToggleSignatures_133
from piltover.tl.types.channels import ChannelParticipants, ChannelParticipant
from piltover.tl.types.messages import Chats, ChatFull as MessagesChatFull, Messages, AffectedMessages, InvitedUsers
from piltover.worker import MessageHandler

handler = MessageHandler("channels")


@handler.on_request(GetChannelRecommendations, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_channel_recommendations():  # pragma: no cover
    return Chats(chats=[])


@handler.on_request(GetAdminedPublicChannels, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_admined_public_channels():  # pragma: no cover
    return Chats(chats=[])


@handler.on_request(CheckUsername)
async def check_username(request: CheckUsername) -> bool:
    request.username = request.username.lower()
    validate_username(request.username)
    if await Username.filter(username=request.username).exists():
        raise ErrorRpc(error_code=400, error_message="USERNAME_OCCUPIED")
    return True


@handler.on_request(UpdateUsername)
async def update_username(request: UpdateUsername, user: User) -> bool:
    peer = await Peer.from_input_peer_raise(user, request.channel)
    if peer.type is not PeerType.CHANNEL:
        raise ErrorRpc(error_code=400, error_message="CHANNEL_INVALID")

    channel = peer.channel

    participant = await ChatParticipant.get_or_none(channel=channel, user=user)
    if not channel.admin_has_permission(participant, ChatAdminRights.CHANGE_INFO):
        raise ErrorRpc(error_code=403, error_message="CHAT_ADMIN_REQUIRED")

    request.username = request.username.lower().strip()
    current_username = await channel.get_username()
    if (not request.username and current_username is None) \
            or (current_username is not None and current_username.username == request.username):
        raise ErrorRpc(error_code=400, error_message="USERNAME_NOT_MODIFIED")

    if request.username:
        validate_username(request.username)
        if await Username.filter(username__iexact=request.username).exists():
            raise ErrorRpc(error_code=400, error_message="USERNAME_OCCUPIED")

    if current_username is not None:
        if not request.username:
            await current_username.delete()
            channel.cached_username = None
        else:
            current_username.username = request.username
            await current_username.save(update_fields=["username"])
    else:
        channel.cached_username = await Username.create(channel=channel, username=request.username)

    await upd.update_channel(peer.channel)
    return True


@handler.on_request(CreateChannel)
async def create_channel(request: CreateChannel, user: User) -> Updates:
    if not request.broadcast and not request.megagroup:
        raise ErrorRpc(error_code=400, error_message="CHANNELS_TOO_MUCH")

    title = request.title.strip()
    description = request.about.strip()
    if not title:
        raise ErrorRpc(error_code=400, error_message="CHAT_TITLE_EMPTY")
    if len(title) > 64:
        raise ErrorRpc(error_code=400, error_message="CHAT_TITLE_EMPTY")
    if len(description) > 255:
        raise ErrorRpc(error_code=400, error_message="CHAT_ABOUT_TOO_LONG")

    channel = await Channel.create(
        creator=user, name=title, description=description, channel=request.broadcast, supergroup=request.megagroup,
    )
    peer_for_user = await Peer.create(owner=user, channel=channel, type=PeerType.CHANNEL)
    await ChatParticipant.create(
        channel=channel, user=user, admin_rights=ChatAdminRights.all() & ~ChatAdminRights.ANONYMOUS,
    )
    await Dialog.get_or_create(peer=peer_for_user)
    peer_channel = await Peer.create(owner=None, channel=channel, type=PeerType.CHANNEL, access_hash=0)
    await SessionManager.subscribe_to_channel(channel.id, [user.id])

    updates = await send_message_internal(
        user, peer_channel, None, None, False,
        author=user, type=MessageType.SERVICE_CHANNEL_CREATE,
        extra_info=MessageActionChannelCreate(title=request.title).write(),
    )

    updates.updates.insert(0, UpdateChannel(channel_id=channel.id))

    return updates


@handler.on_request(GetChannels)
async def get_channels(request: GetChannels, user: User) -> Chats:
    channels = []
    for input_channel in request.id:
        if isinstance(input_channel, InputChannelEmpty):
            channels.append(ChatEmpty(id=0))
        elif isinstance(input_channel, (InputChannel, InputChannelFromMessage)):
            # TODO: search for channel in list of channels where user is a member if input_channel.access_hash == 0
            channel = await Channel.get_or_none(id=input_channel.channel_id, chatparticipants__user=user)
            if channel is None:
                channels.append(ChatEmpty(id=0))
            else:
                channels.append(await channel.to_tl(user))

    return Chats(chats=channels)


@handler.on_request(GetFullChannel)
async def get_full_channel(request: GetFullChannel, user: User) -> MessagesChatFull:
    peer = await Peer.from_input_peer_raise(user, request.channel)
    if peer.type is not PeerType.CHANNEL:
        raise ErrorRpc(error_code=400, error_message="CHANNEL_INVALID")

    channel = peer.channel

    photo = PhotoEmpty(id=0)
    if channel.photo_id:
        channel.photo = await channel.photo
        photo = await channel.photo.to_tl_photo(user)

    # TODO: full_chat.exported_invite
    # TODO: full_chat.migrated_from_chat_id and full_chat.migrated_from_max_id
    # TODO: full_chat.available_min_id
    in_read_max_id, out_read_max_id, unread_count, _, _ = await ReadState.get_in_out_ids_and_unread(
        peer, True, True,
    )
    return MessagesChatFull(
        full_chat=ChannelFull(
            can_view_participants=False,  # TODO: allow viewing participants
            can_set_username=True,
            can_set_stickers=False,
            hidden_prehistory=False,  # TODO: hide history for new users
            can_set_location=False,
            has_scheduled=False,  # TODO: change when scheduled messages will be added
            can_view_stats=False,
            can_delete_channel=True,
            antispam=False,
            participants_hidden=True,  # TODO: allow viewing participants
            translations_disabled=True,
            restricted_sponsored=True,
            can_view_revenue=False,

            id=channel.id,
            about=channel.description,
            participants_count=await ChatParticipant.filter(channel=channel).count(),
            admins_count=await ChatParticipant.filter(channel=channel, admin_rights__gt=0).count(),
            read_inbox_max_id=in_read_max_id,
            read_outbox_max_id=out_read_max_id,
            unread_count=unread_count,
            chat_photo=photo,
            notify_settings=PeerNotifySettings(),
            bot_info=[],
            pinned_msg_id=cast(
                int | None,
                await Message.filter(
                    peer__owner=None, peer__channel=channel, pinned=True
                ).order_by("-id").first().values_list("id", flat=True)
            ),
            pts=channel.pts,
        ),
        chats=[await channel.to_tl(user)],
        users=[await user.to_tl(user)],
    )


@handler.on_request(EditTitle)
async def edit_channel_title(request: EditTitle, user: User) -> Updates:
    peer = await Peer.from_input_peer_raise(user, request.channel)
    if peer.type is not PeerType.CHANNEL:
        raise ErrorRpc(error_code=400, error_message="CHANNEL_INVALID")

    participant = await ChatParticipant.get_or_none(channel=peer.channel, user=user)
    if not peer.channel.admin_has_permission(participant, ChatAdminRights.CHANGE_INFO):
        raise ErrorRpc(error_code=403, error_message="CHAT_ADMIN_REQUIRED")

    await peer.channel.update(title=request.title)

    updates = await upd.update_channel(peer.channel, user)
    updates_msg = await send_message_internal(
        user, peer, None, None, False,
        author=user, type=MessageType.SERVICE_CHAT_EDIT_TITLE,
        extra_info=MessageActionChatEditTitle(title=request.title).write(),
    )
    updates.updates.extend(updates_msg.updates)
    updates.users.extend(updates_msg.users)
    updates.chats.extend(updates_msg.chats)

    return updates


@handler.on_request(EditPhoto)
async def edit_channel_photo(request: EditPhoto, user: User):
    peer = await Peer.from_input_peer_raise(user, request.channel)
    if peer.type is not PeerType.CHANNEL:
        raise ErrorRpc(error_code=400, error_message="CHANNEL_INVALID")

    participant = await ChatParticipant.get_or_none(channel=peer.channel, user=user)
    if not peer.channel.admin_has_permission(participant, ChatAdminRights.CHANGE_INFO):
        raise ErrorRpc(error_code=403, error_message="CHAT_ADMIN_REQUIRED")

    channel = peer.channel
    await channel.update(photo=await resolve_input_chat_photo(user, request.photo))

    updates = await upd.update_channel(peer.channel, user)
    updates_msg = await send_message_internal(
        user, peer, None, None, False,
        author=user, type=MessageType.SERVICE_CHAT_EDIT_PHOTO,
        extra_info=Long.write(channel.photo.id if channel.photo else 0),
    )
    updates.updates.extend(updates_msg.updates)
    updates.users.extend(updates_msg.users)
    updates.chats.extend(updates_msg.chats)

    return updates


@handler.on_request(GetMessages)
async def get_messages(request: GetMessages, user: User) -> Messages:
    peer = await Peer.from_input_peer_raise(user, request.channel)
    if peer.type is not PeerType.CHANNEL:
        raise ErrorRpc(error_code=400, error_message="CHANNEL_INVALID")
    await peer.channel.get_participant_raise(user)

    query = Q()

    for message_query in request.id:
        if isinstance(message_query, InputMessageID):
            query |= Q(id=message_query.id)
        elif isinstance(message_query, InputMessageReplyTo):
            query |= Q(id=Subquery(
                Message.filter(
                    peer__channel=peer.channel, id=message_query.id
                ).first().values_list("reply_to__id", flat=True)
            ))

    query &= Q(peer__channel=peer.channel)

    return await format_messages_internal(user, await Message.filter(query))


@handler.on_request(DeleteMessages)
async def delete_messages(request: DeleteMessages, user: User) -> AffectedMessages:
    peer = await Peer.from_input_peer_raise(user, request.channel)
    if peer.type is not PeerType.CHANNEL:
        raise ErrorRpc(error_code=400, error_message="CHANNEL_INVALID")
    participant = await peer.channel.get_participant_raise(user)
    if not peer.channel.admin_has_permission(participant, ChatAdminRights.DELETE_MESSAGES):
        raise ErrorRpc(error_code=403, error_message="MESSAGE_DELETE_FORBIDDEN")

    ids = request.id[:100]
    message_ids: list[int] = await Message.filter(
        Q(id__in=ids, peer__channel=peer.channel) & (Q(peer__owner=user) | Q(peer__owner=None))
    ).values_list("id", flat=True)

    if not message_ids:
        return AffectedMessages(pts=peer.channel.pts, pts_count=0)

    await Message.filter(id__in=message_ids).delete()
    pts = await upd.delete_messages_channel(peer.channel, message_ids)

    return AffectedMessages(pts=pts, pts_count=len(message_ids))


@handler.on_request(EditBanned)
async def edit_banned(request: EditBanned, user: User):
    peer = await Peer.from_input_peer_raise(user, request.channel)
    if peer.type is not PeerType.CHANNEL:
        raise ErrorRpc(error_code=400, error_message="CHANNEL_INVALID")
    participant = await peer.channel.get_participant_raise(user)
    if not peer.channel.admin_has_permission(participant, ChatAdminRights.BAN_USERS):
        raise ErrorRpc(error_code=403, error_message="RIGHT_FORBIDDEN")

    target_peer = await Peer.from_input_peer_raise(user, request.participant)
    if target_peer.type is not PeerType.USER:
        raise ErrorRpc(error_code=400, error_message="PARTICIPANT_ID_INVALID")
    target_participant = await ChatParticipant.get_or_none(user=target_peer.user, channel=peer.channel)
    if target_participant is None:
        raise ErrorRpc(error_code=400, error_message="PARTICIPANT_ID_INVALID")

    # TODO: check if target_participant is not admin

    new_banned_rights = ChatBannedRights.from_tl(request.banned_rights)
    if target_participant.banned_rights == new_banned_rights:
        return Updates(updates=[], users=[], chats=[], date=int(time()), seq=0)

    target_participant.banned_rights = new_banned_rights
    await target_participant.save(update_fields=["banned_rights"])

    await upd.update_channel_for_user(peer.channel, target_peer.user)
    return Updates(
        updates=[UpdateChannel(channel_id=peer.channel.id)],
        users=[],
        chats=[await peer.channel.to_tl(user)],
        date=int(time()),
        seq=0,
    )


@handler.on_request(EditAdmin)
async def edit_admin(request: EditAdmin, user: User):
    peer = await Peer.from_input_peer_raise(user, request.channel)
    if peer.type is not PeerType.CHANNEL:
        raise ErrorRpc(error_code=400, error_message="CHANNEL_INVALID")
    participant = await peer.channel.get_participant_raise(user)
    if not peer.channel.admin_has_permission(participant, ChatAdminRights.ADD_ADMINS):
        raise ErrorRpc(error_code=403, error_message="RIGHT_FORBIDDEN")

    target_peer = await Peer.from_input_peer_raise(user, request.user_id)
    if target_peer.type is not PeerType.USER:
        raise ErrorRpc(error_code=400, error_message="PARTICIPANT_ID_INVALID")
    if target_peer.user_id == peer.channel.creator_id and target_peer.user != user:
        raise ErrorRpc(error_code=400, error_message="USER_CREATOR")
    target_participant = await ChatParticipant.get_or_none(user=target_peer.user, channel=peer.channel)
    if target_participant is None:
        raise ErrorRpc(error_code=400, error_message="PARTICIPANT_ID_INVALID")

    new_admin_rights = ChatAdminRights.from_tl(request.admin_rights)

    if user.id != peer.channel.creator_id:
        for new_right in new_admin_rights:
            if not (participant.admin_rights & new_right):
                raise ErrorRpc(error_code=403, error_message="RIGHT_FORBIDDEN")

    if target_participant.admin_rights == new_admin_rights and target_participant.admin_rank == request.rank:
        return Updates(updates=[], users=[], chats=[], date=int(time()), seq=0)

    update_fields = []
    if request.rank != target_participant.admin_rank:
        target_participant.admin_rank = request.rank
        update_fields.append("admin_rank")
    if new_admin_rights != target_participant.admin_rights:
        target_participant.admin_rights = new_admin_rights
        update_fields.append("admin_rights")
    if not target_participant.promoted_by_id:
        target_participant.promoted_by_id = user.id
        update_fields.append("promoted_by_id")

    await target_participant.save(update_fields=update_fields)

    await upd.update_channel_for_user(peer.channel, target_peer.user)
    return Updates(
        updates=[UpdateChannel(channel_id=peer.channel.id)],
        users=[],
        chats=[await peer.channel.to_tl(user)],
        date=int(time()),
        seq=0,
    )


@handler.on_request(GetParticipants)
async def get_participants(request: GetParticipants, user: User):
    peer = await Peer.from_input_peer_raise(user, request.channel)
    if peer.type is not PeerType.CHANNEL:
        raise ErrorRpc(error_code=400, error_message="CHANNEL_INVALID")
    participant = await peer.channel.get_participant_raise(user)
    if not peer.channel.admin_has_permission(participant, ChatAdminRights.INVITE_USERS):
        raise ErrorRpc(error_code=403, error_message="CHAT_ADMIN_REQUIRED")

    if isinstance(request.filter, ChannelParticipantsRecent):
        query = Q(channel=peer.channel)
    elif isinstance(request.filter, ChannelParticipantsAdmins):
        query = Q(channel=peer.channel, admin_rights__gt=0)
    elif isinstance(request.filter, ChannelParticipantsSearch):
        query = Q(channel=peer.channel, user__first_name__icontains=request.filter.q)
    else:
        # TODO: ChannelParticipantsContacts, ChannelParticipantsMentions
        return ChannelParticipants(count=0, participants=[], chats=[], users=[])

    limit = max(min(request.limit, 100), 1)
    participants = await ChatParticipant.filter(query).select_related("user").limit(limit).offset(request.offset)

    participants_tl = []
    users_tl = []

    for participant in participants:
        participant.channel = peer.channel
        participants_tl.append(await participant.to_tl_channel(user))
        users_tl.append(await participant.user.to_tl(user))

    return ChannelParticipants(
        count=await ChatParticipant.filter(query).count(),
        participants=participants_tl,
        chats=[await peer.channel.to_tl(user)],
        users=users_tl,
    )


@handler.on_request(GetParticipant)
async def get_participant(request: GetParticipant, user: User):
    peer = await Peer.from_input_peer_raise(user, request.channel)
    if peer.type is not PeerType.CHANNEL:
        raise ErrorRpc(error_code=400, error_message="CHANNEL_INVALID")
    participant = await peer.channel.get_participant_raise(user)
    if not peer.channel.admin_has_permission(participant, ChatAdminRights.INVITE_USERS):
        raise ErrorRpc(error_code=403, error_message="CHAT_ADMIN_REQUIRED")

    target_peer = await Peer.from_input_peer_raise(user, request.participant)
    if target_peer.type is not PeerType.USER:
        raise ErrorRpc(error_code=400, error_message="PARTICIPANT_ID_INVALID")
    target_participant = await ChatParticipant.get_or_none(
        user=target_peer.user, channel=peer.channel,
    ).select_related("user")
    if target_participant is None:
        raise ErrorRpc(error_code=400, error_message="USER_NOT_PARTICIPANT")

    return ChannelParticipant(
        participant=await target_participant.to_tl_channel(user),
        chats=[await peer.channel.to_tl(user)],
        users=[await target_participant.user.to_tl(user)],
    )


@handler.on_request(ReadHistory)
async def read_channel_history(request: ReadHistory, user: User) -> bool:
    peer = await Peer.from_input_peer_raise(user, request.channel)
    if peer.type is not PeerType.CHANNEL:
        raise ErrorRpc(error_code=400, error_message="CHANNEL_INVALID")

    read_state, created = await ReadState.get_or_create(peer=peer)
    if request.max_id <= read_state.last_message_id:
        return True

    message_id, internal_id = await Message.filter(
        id__lte=request.max_id, peer__owner=None, peer__channel=peer.channel,
    ).order_by("-id").first().values_list("id", "internal_id")
    if not message_id:
        return True

    unread_count = await Message.filter(peer__owner=None, peer__channel=peer.channel, id__gt=message_id).count()

    read_state.last_message_id = message_id
    await read_state.save(update_fields=["last_message_id"])

    # TODO: create and send outbox read update if supergroup

    await upd.update_read_history_inbox_channel(peer, message_id, unread_count)

    return True


@handler.on_request(InviteToChannel_133)
@handler.on_request(InviteToChannel)
async def invite_to_channel(request: InviteToChannel, user: User):
    peer = await Peer.from_input_peer_raise(user, request.channel)
    if peer.type is not PeerType.CHANNEL:
        raise ErrorRpc(error_code=400, error_message="CHANNEL_INVALID")
    participant = await peer.channel.get_participant_raise(user)
    if not peer.channel.user_has_permission(participant, ChatBannedRights.INVITE_USERS) and \
            not peer.channel.admin_has_permission(participant, ChatAdminRights.INVITE_USERS):
        raise ErrorRpc(error_code=403, error_message="CHAT_ADMIN_REQUIRED")

    added_users = []
    peers_to_create = []
    participants_to_create = []

    for input_user in request.users[:100]:
        user_peer = await Peer.from_input_peer_raise(user, input_user)
        if user_peer.type is not PeerType.USER:
            raise ErrorRpc(error_code=400, error_message="USER_ID_INVALID")
        if await ChatParticipant.filter(user=user_peer.user, channel=peer.channel).exists():
            continue
        if not await PrivacyRule.has_access_to(user, user_peer.user, PrivacyRuleKeyType.CHAT_INVITE):
            raise ErrorRpc(error_code=403, error_message="USER_PRIVACY_RESTRICTED")

        added_users.append(user_peer.user)
        peers_to_create.append(Peer(owner=user_peer.user, channel=peer.channel, type=PeerType.CHANNEL))
        participants_to_create.append(ChatParticipant(user=user_peer.user, channel=peer.channel, inviter_id=user.id))

    await Peer.bulk_create(peers_to_create, ignore_conflicts=True)
    await ChatParticipant.bulk_create(participants_to_create, ignore_conflicts=True)
    await ChatInviteRequest.filter(id__in=Subquery(
        ChatInviteRequest.filter(
            user__id__in=[added_user.id for added_user in added_users], invite__channel=peer.channel,
        ).values_list("id", flat=True)
    )).delete()

    await SessionManager.subscribe_to_channel(peer.channel.id, [added_user.id for added_user in added_users])

    for added_user in added_users:
        await upd.update_channel_for_user(peer.channel, added_user)

    return InvitedUsers(
        updates=Updates(
            updates=[UpdateChannel(channel_id=peer.channel.id)],
            chats=[await peer.channel.to_tl(user)],
            users=[],
            date=int(time()),
            seq=0,
        ),
        missing_invitees=[],
    )


@handler.on_request(ToggleSignatures_133)
@handler.on_request(ToggleSignatures)
async def toggle_signatures(request: ToggleSignatures, user: User):
    peer = await Peer.from_input_peer_raise(user, request.channel)
    if peer.type is not PeerType.CHANNEL:
        raise ErrorRpc(error_code=400, error_message="CHANNEL_INVALID")

    participant = await ChatParticipant.get_or_none(channel=peer.channel, user=user)
    if not peer.channel.admin_has_permission(participant, ChatAdminRights.CHANGE_INFO):
        raise ErrorRpc(error_code=403, error_message="CHAT_ADMIN_REQUIRED")

    channel = peer.channel
    if channel.signatures == request.signatures_enabled:
        raise ErrorRpc(error_code=400, error_message="CHAT_NOT_MODIFIED")

    channel.signatures = request.signatures_enabled
    channel.version += 1
    await channel.save(update_fields=["signatures", "version"])

    return await upd.update_channel(channel, user)


@handler.on_request(ToggleSignatures_133)
async def toggle_signatures_136(request: ToggleSignatures_133, user: User):
    return await toggle_signatures(ToggleSignatures(
        signatures_enabled=request.enabled,
        profiles_enabled=False,
        channel=request.channel,
    ), user)
