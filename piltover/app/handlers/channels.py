from time import time
from typing import cast

from tortoise.expressions import Q, Subquery
from tortoise.transactions import in_transaction

import piltover.app.utils.updates_manager as upd
from piltover.app.handlers.messages.chats import resolve_input_chat_photo
from piltover.app.handlers.messages.history import format_messages_internal
from piltover.app.handlers.messages.invites import user_join_chat_or_channel
from piltover.app.handlers.messages.sending import send_message_internal
from piltover.app.utils.utils import validate_username, check_password_internal
from piltover.app_config import AppConfig
from piltover.context import request_ctx
from piltover.db.enums import MessageType, PeerType, ChatBannedRights, ChatAdminRights, PrivacyRuleKeyType, \
    AdminLogEntryAction
from piltover.db.models import User, Channel, Peer, Dialog, ChatParticipant, Message, ReadState, PrivacyRule, \
    ChatInviteRequest, Username, ChatInvite, AvailableChannelReaction, Reaction, UserPassword, UserPersonalChannel, Chat
from piltover.db.models.admin_log_entry import AdminLogEntry
from piltover.db.models.channel import CREATOR_RIGHTS
from piltover.db.models.message import append_channel_min_message_id_to_query_maybe
from piltover.enums import ReqHandlerFlags
from piltover.exceptions import ErrorRpc, Unreachable
from piltover.session_manager import SessionManager
from piltover.tl import MessageActionChannelCreate, UpdateChannel, Updates, \
    InputChannelFromMessage, InputChannel, ChannelFull, PhotoEmpty, PeerNotifySettings, MessageActionChatEditTitle, \
    InputMessageID, InputMessageReplyTo, ChannelParticipantsRecent, ChannelParticipantsAdmins, \
    ChannelParticipantsSearch, ChatReactionsAll, ChatReactionsNone, ChatReactionsSome, ReactionEmoji, \
    ReactionCustomEmoji, SendAsPeer, PeerUser, PeerChannel, MessageActionChatEditPhoto, InputUserSelf, InputUser, \
    InputUserFromMessage
from piltover.tl.functions.channels import GetChannelRecommendations, GetAdminedPublicChannels, CheckUsername, \
    CreateChannel, GetChannels, GetFullChannel, EditTitle, EditPhoto, GetMessages, DeleteMessages, EditBanned, \
    EditAdmin, GetParticipants, GetParticipant, ReadHistory, InviteToChannel, InviteToChannel_133, ToggleSignatures, \
    UpdateUsername, ToggleSignatures_133, GetMessages_40, DeleteChannel, EditCreator, JoinChannel, LeaveChannel, \
    TogglePreHistoryHidden, ToggleJoinToSend, GetSendAs, GetSendAs_135, GetAdminLog, ToggleJoinRequest, \
    GetGroupsForDiscussion, SetDiscussionGroup
from piltover.tl.functions.messages import SetChatAvailableReactions, SetChatAvailableReactions_136, \
    SetChatAvailableReactions_145, SetChatAvailableReactions_179
from piltover.tl.types.channels import ChannelParticipants, ChannelParticipant, SendAsPeers, AdminLogResults
from piltover.tl.types.messages import Chats, ChatFull as MessagesChatFull, Messages, AffectedMessages, InvitedUsers
from piltover.worker import MessageHandler

handler = MessageHandler("channels")


@handler.on_request(GetChannelRecommendations, ReqHandlerFlags.AUTH_NOT_REQUIRED | ReqHandlerFlags.BOT_NOT_ALLOWED)
async def get_channel_recommendations():  # pragma: no cover
    return Chats(chats=[])


@handler.on_request(CheckUsername, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def check_username(request: CheckUsername) -> bool:
    request.username = request.username.lower()
    validate_username(request.username)
    if await Username.filter(username=request.username).exists():
        raise ErrorRpc(error_code=400, error_message="USERNAME_OCCUPIED")
    return True


@handler.on_request(UpdateUsername, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def update_username(request: UpdateUsername, user: User) -> bool:
    peer = await Peer.from_input_peer_raise(
        user, request.channel, message="CHANNEL_PRIVATE", code=406, peer_types=(PeerType.CHANNEL,),
    )

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

    old_username = ""
    new_username = request.username

    if current_username is not None:
        old_username = current_username.username
        if not request.username:
            await current_username.delete()
            await UserPersonalChannel.filter(channel=channel).delete()
            channel.cached_username = None
        else:
            current_username.username = request.username
            await current_username.save(update_fields=["username"])
    else:
        channel.cached_username = await Username.create(channel=channel, username=request.username)

    await AdminLogEntry.create(
        channel=peer.channel,
        user=user,
        action=AdminLogEntryAction.CHANGE_USERNAME,
        prev=old_username.encode("utf8"),
        new=new_username.encode("utf8"),
    )

    if channel.cached_username is not None and channel.hidden_prehistory:
        channel.min_available_id = cast(
            int | None,
            await Message.filter(
                peer__owner=None, peer__channel=channel,
            ).order_by("-id").first().values_list("id", flat=True)
        )
        if channel.min_available_id is not None:
            channel.min_available_id += 1
        channel.hidden_prehistory = False
        await channel.save(update_fields=["min_available_id", "hidden_prehistory"])

    await upd.update_channel(peer.channel)
    return True


@handler.on_request(CreateChannel, ReqHandlerFlags.BOT_NOT_ALLOWED)
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
        channel=channel, user=user, admin_rights=ChatAdminRights.from_tl(CREATOR_RIGHTS),
    )
    await Dialog.create_or_unhide(peer_for_user)
    peer_channel = await Peer.create(owner=None, channel=channel, type=PeerType.CHANNEL)
    await SessionManager.subscribe_to_channel(channel.id, [user.id])

    updates = await send_message_internal(
        user, peer_channel, None, None, False,
        author=user, type=MessageType.SERVICE_CHANNEL_CREATE,
        extra_info=MessageActionChannelCreate(title=request.title).write(),
    )

    updates.updates.insert(0, UpdateChannel(channel_id=channel.make_id()))

    return updates


@handler.on_request(GetChannels)
async def get_channels(request: GetChannels, user: User) -> Chats:
    ctx = request_ctx.get()
    channels_q = Q()

    for input_channel in request.id:
        if not isinstance(input_channel, (InputChannel, InputChannelFromMessage)):
            continue

        channel_id = Channel.norm_id(input_channel.channel_id)

        if isinstance(input_channel, InputChannel):
            if input_channel.access_hash == 0:
                channels_q |= Q(id=channel_id, chatparticipants__user=user)
            else:
                if not Channel.check_access_hash(user.id, ctx.auth_id, channel_id, input_channel.access_hash):
                    continue
                channels_q |= Q(peers__owner=user, peers__channel__id=channel_id)
        elif isinstance(input_channel, InputChannelFromMessage):
            ...  # TODO: support channels from message

    if not channels_q.children:
        return Chats(chats=[])

    return Chats(chats=[
        await channel.to_tl(user)
        for channel in await Channel.filter(channels_q)
    ])


@handler.on_request(GetFullChannel)
async def get_full_channel(request: GetFullChannel, user: User) -> MessagesChatFull:
    peer = await Peer.from_input_peer_raise(
        user, request.channel, message="CHANNEL_PRIVATE", code=406, peer_types=(PeerType.CHANNEL,)
    )

    channel = peer.channel

    photo = PhotoEmpty(id=0)
    if channel.photo_id:
        channel.photo = await channel.photo
        photo = channel.photo.to_tl_photo()

    invite = None
    participant = await ChatParticipant.get_or_none(channel=channel, user=user)
    if participant is not None and channel.admin_has_permission(participant, ChatAdminRights.INVITE_USERS):
        invite = await ChatInvite.get_or_create_permanent(user, peer.channel)

    in_read_max_id, out_read_max_id, unread_count, _, _ = await ReadState.get_in_out_ids_and_unread(
        peer, True, True,
    )

    if channel.all_reactions:
        available_reactions = ChatReactionsAll(allow_custom=channel.all_reactions_custom)
    else:
        some = await AvailableChannelReaction.filter(channel=channel).select_related("reaction")
        some = [ReactionEmoji(emoticon=reaction.reaction.reaction) for reaction in some]
        if some:
            available_reactions = ChatReactionsSome(reactions=some)
        else:
            available_reactions = ChatReactionsNone()

    has_scheduled = False
    if participant is not None and channel.admin_has_permission(participant, ChatAdminRights.POST_MESSAGES):
        has_scheduled = await Message.filter(
            peer__owner=user, peer__channel=channel, scheduled_date__not_isnull=True,
        ).exists()

    can_change_info = participant is not None and channel.admin_has_permission(participant, ChatAdminRights.CHANGE_INFO)

    min_message_id: int | None = None
    if channel.hidden_prehistory and participant is not None and participant.min_message_id:
        min_message_id = cast(
            int | None,
            await Message.filter(
                peer__owner=None, peer__channel=channel, id__gte=participant.min_message_id,
            ).order_by("id").first().values_list("id", flat=True)
        )

    migrated_from_chat_id = migrated_from_max_id = None
    if channel.migrated_from_id is not None \
            and (chat_peer := await Peer.get_or_none(owner=user, chat__id=channel.migrated_from_id)) is not None:
        migrated_from_chat_id = channel.migrated_from_id
        migrated_from_max_id = await Message.filter(peer=chat_peer).order_by("-id").first().values_list("id", flat=True)

    return MessagesChatFull(
        full_chat=ChannelFull(
            can_view_participants=False,  # TODO: allow viewing participants
            can_set_username=can_change_info,
            can_set_stickers=False,
            hidden_prehistory=channel.hidden_prehistory,
            can_set_location=False,
            has_scheduled=has_scheduled,
            can_view_stats=False,
            can_delete_channel=channel.creator_id == user.id,
            antispam=False,
            participants_hidden=True,  # TODO: allow viewing participants
            translations_disabled=True,
            restricted_sponsored=True,
            can_view_revenue=False,

            id=channel.make_id(),
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
            exported_invite=await invite.to_tl() if invite is not None else None,
            available_reactions=available_reactions,
            ttl_period=channel.ttl_period_days * 86400 if channel.ttl_period_days else None,
            available_min_id=min_message_id,
            migrated_from_chat_id=Chat.make_id_from(migrated_from_chat_id) if migrated_from_chat_id else None,
            migrated_from_max_id=migrated_from_max_id,
            # TODO: linked_chat_id
            # linked_chat_id=...,
        ),
        chats=[await channel.to_tl(user)],
        users=[await user.to_tl(user)],
    )


@handler.on_request(EditTitle)
async def edit_channel_title(request: EditTitle, user: User) -> Updates:
    peer = await Peer.from_input_peer_raise(
        user, request.channel, message="CHANNEL_PRIVATE", code=406, peer_types=(PeerType.CHANNEL,)
    )

    participant = await ChatParticipant.get_or_none(channel=peer.channel, user=user)
    if not peer.channel.admin_has_permission(participant, ChatAdminRights.CHANGE_INFO):
        raise ErrorRpc(error_code=403, error_message="CHAT_ADMIN_REQUIRED")

    old_title = peer.channel.name
    await peer.channel.update(title=request.title)

    await AdminLogEntry.create(
        channel=peer.channel,
        user=user,
        action=AdminLogEntryAction.CHANGE_TITLE,
        prev=old_title.encode("utf8"),
        new=peer.channel.name.encode("utf8"),
    )

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
    peer = await Peer.from_input_peer_raise(
        user, request.channel, message="CHANNEL_PRIVATE", code=406, peer_types=(PeerType.CHANNEL,),
        select_related=("channel__photo",),
    )

    participant = await ChatParticipant.get_or_none(channel=peer.channel, user=user)
    if not peer.channel.admin_has_permission(participant, ChatAdminRights.CHANGE_INFO):
        raise ErrorRpc(error_code=403, error_message="CHAT_ADMIN_REQUIRED")

    channel = peer.channel
    old_photo = channel.photo
    await channel.update(photo=await resolve_input_chat_photo(user, request.photo))

    await AdminLogEntry.create(
        channel=peer.channel,
        user=user,
        action=AdminLogEntryAction.CHANGE_PHOTO,
        old_photo=old_photo,
        new_photo=channel.photo,
    )

    updates = await upd.update_channel(peer.channel, user)
    updates_msg = await send_message_internal(
        user, peer, None, None, False,
        author=user, type=MessageType.SERVICE_CHAT_EDIT_PHOTO,
        extra_info=MessageActionChatEditPhoto(
            photo=channel.photo.to_tl_photo() if channel.photo else PhotoEmpty(id=0),
        ).write(),
    )
    updates.updates.extend(updates_msg.updates)
    updates.users.extend(updates_msg.users)
    updates.chats.extend(updates_msg.chats)

    return updates


@handler.on_request(GetMessages_40)
@handler.on_request(GetMessages)
async def get_messages(request: GetMessages, user: User) -> Messages:
    peer = await Peer.from_input_peer_raise(
        user, request.channel, message="CHANNEL_PRIVATE", code=406, peer_types=(PeerType.CHANNEL,)
    )

    if not await Username.filter(channel=peer.channel).exists() and await peer.channel.get_participant(user) is None:
        raise ErrorRpc(error_code=400, error_message="CHAT_RESTRICTED")

    query = Q(id=0)

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
    query = await append_channel_min_message_id_to_query_maybe(peer, query)

    return await format_messages_internal(user, await Message.filter(query).select_related("peer"))


@handler.on_request(DeleteMessages)
async def delete_messages(request: DeleteMessages, user: User) -> AffectedMessages:
    peer = await Peer.from_input_peer_raise(
        user, request.channel, message="CHANNEL_PRIVATE", code=406, peer_types=(PeerType.CHANNEL,)
    )
    participant = await peer.channel.get_participant_raise(user)
    if not peer.channel.admin_has_permission(participant, ChatAdminRights.DELETE_MESSAGES):
        raise ErrorRpc(error_code=403, error_message="MESSAGE_DELETE_FORBIDDEN")

    ids = request.id[:100]
    ids_query = Q(id__in=ids, peer__channel=peer.channel) & (Q(peer__owner=user) | Q(peer__owner=None))
    ids_query = await append_channel_min_message_id_to_query_maybe(peer, ids_query, participant)
    message_ids: list[int] = await Message.filter(ids_query).values_list("id", flat=True)

    if not message_ids:
        return AffectedMessages(pts=peer.channel.pts, pts_count=0)

    await Message.filter(id__in=message_ids).delete()
    pts = await upd.delete_messages_channel(peer.channel, message_ids)

    return AffectedMessages(pts=pts, pts_count=len(message_ids))


@handler.on_request(EditBanned)
async def edit_banned(request: EditBanned, user: User):
    peer = await Peer.from_input_peer_raise(
        user, request.channel, message="CHANNEL_PRIVATE", code=406, peer_types=(PeerType.CHANNEL,)
    )
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
        updates=[UpdateChannel(channel_id=peer.channel.make_id())],
        users=[],
        chats=[await peer.channel.to_tl(user)],
        date=int(time()),
        seq=0,
    )


@handler.on_request(EditAdmin)
async def edit_admin(request: EditAdmin, user: User):
    peer = await Peer.from_input_peer_raise(
        user, request.channel, message="CHANNEL_PRIVATE", code=406, peer_types=(PeerType.CHANNEL,)
    )
    channel = peer.channel

    participant = await channel.get_participant_raise(user)
    if not channel.admin_has_permission(participant, ChatAdminRights.ADD_ADMINS):
        raise ErrorRpc(error_code=403, error_message="RIGHT_FORBIDDEN")

    target_peer = await Peer.from_input_peer_raise(
        user, request.user_id, "PARTICIPANT_ID_INVALID", peer_types=(PeerType.USER, PeerType.SELF,)
    )
    if target_peer.user_id == channel.creator_id and target_peer.user_id != user.id:
        raise ErrorRpc(error_code=400, error_message="USER_CREATOR")
    target_participant = await ChatParticipant.get_or_none(user__id=target_peer.user_id, channel=channel)
    if target_participant is None:
        raise ErrorRpc(error_code=400, error_message="PARTICIPANT_ID_INVALID")

    new_admin_rights = ChatAdminRights.from_tl(request.admin_rights)
    if target_peer.user_id == channel.creator_id:
        new_admin_rights |= ChatAdminRights.from_tl(CREATOR_RIGHTS)

    if user.id != channel.creator_id:
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

    await upd.update_channel_for_user(channel, target_peer.peer_user(user))
    return Updates(
        updates=[UpdateChannel(channel_id=channel.make_id())],
        users=[],
        chats=[await channel.to_tl(user)],
        date=int(time()),
        seq=0,
    )


@handler.on_request(GetParticipants)
async def get_participants(request: GetParticipants, user: User):
    peer = await Peer.from_input_peer_raise(
        user, request.channel, message="CHANNEL_PRIVATE", code=406, peer_types=(PeerType.CHANNEL,)
    )
    participant = await peer.channel.get_participant(user)
    if participant is None or not peer.channel.admin_has_permission(participant, ChatAdminRights.INVITE_USERS):
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

    peers_to_create = []

    for participant in participants:
        if participant.user != user:
            peers_to_create.append(Peer(owner=user, user=participant.user, type=PeerType.USER))

    await Peer.bulk_create(peers_to_create, ignore_conflicts=True)

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
    peer = await Peer.from_input_peer_raise(
        user, request.channel, message="CHANNEL_PRIVATE", code=406, peer_types=(PeerType.CHANNEL,)
    )
    participant = await peer.channel.get_participant(user)
    if participant is None:
        raise ErrorRpc(error_code=400, error_message="USER_NOT_PARTICIPANT")

    target_peer = await Peer.from_input_peer_raise(user, request.participant)
    if target_peer.type is not PeerType.USER:
        raise ErrorRpc(error_code=400, error_message="PARTICIPANT_ID_INVALID")

    # TODO: check if you can request info about self if you are not an admin
    if not peer.channel.admin_has_permission(participant, ChatAdminRights.INVITE_USERS) \
            and target_peer.type is not PeerType.SELF:
        raise ErrorRpc(error_code=403, error_message="CHAT_ADMIN_REQUIRED")

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


@handler.on_request(ReadHistory, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def read_channel_history(request: ReadHistory, user: User) -> bool:
    peer = await Peer.from_input_peer_raise(
        user, request.channel, message="CHANNEL_PRIVATE", code=406, peer_types=(PeerType.CHANNEL,)
    )

    read_state, created = await ReadState.get_or_create(peer=peer)
    if request.max_id <= read_state.last_message_id:
        return True

    unread_ids = await Message.filter(
        id__lte=request.max_id, peer__owner=None, peer__channel=peer.channel,
    ).order_by("-id").first().values_list("id", "internal_id")
    if not unread_ids:
        return True

    message_id, internal_id = unread_ids
    if not message_id:
        return True

    unread_count = await Message.filter(peer__owner=None, peer__channel=peer.channel, id__gt=message_id).count()

    read_state.last_message_id = message_id
    await read_state.save(update_fields=["last_message_id"])

    # TODO: create and send outbox read update if supergroup

    await upd.update_read_history_inbox_channel(peer, message_id, unread_count)

    return True


@handler.on_request(InviteToChannel_133, ReqHandlerFlags.BOT_NOT_ALLOWED)
@handler.on_request(InviteToChannel, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def invite_to_channel(request: InviteToChannel, user: User):
    peer = await Peer.from_input_peer_raise(
        user, request.channel, message="CHANNEL_PRIVATE", code=406, peer_types=(PeerType.CHANNEL,)
    )

    channel = peer.channel
    participant = await channel.get_participant_raise(user)
    if not channel.user_has_permission(participant, ChatBannedRights.INVITE_USERS) and \
            not channel.admin_has_permission(participant, ChatAdminRights.INVITE_USERS):
        raise ErrorRpc(error_code=403, error_message="CHAT_ADMIN_REQUIRED")

    added_users = []
    peers_to_create = []
    participants_to_create = []

    for input_user in request.users[:100]:
        user_peer = await Peer.from_input_peer_raise(user, input_user)
        if user_peer.type is not PeerType.USER:
            raise ErrorRpc(error_code=400, error_message="USER_ID_INVALID")
        if await ChatParticipant.filter(user=user_peer.user, channel=channel).exists():
            continue
        if not await PrivacyRule.has_access_to(user, user_peer.user, PrivacyRuleKeyType.CHAT_INVITE):
            raise ErrorRpc(error_code=403, error_message="USER_PRIVACY_RESTRICTED")

        added_users.append(user_peer.user)
        peers_to_create.append(Peer(owner=user_peer.user, channel=channel, type=PeerType.CHANNEL))
        participants_to_create.append(ChatParticipant(
            user=user_peer.user, channel=channel, inviter_id=user.id, min_message_id=channel.min_available_id,
        ))

    await Peer.bulk_create(peers_to_create, ignore_conflicts=True)
    await ChatParticipant.bulk_create(participants_to_create, ignore_conflicts=True)
    await ChatInviteRequest.filter(id__in=Subquery(
        ChatInviteRequest.filter(
            user__id__in=[added_user.id for added_user in added_users], invite__channel=channel,
        ).values_list("id", flat=True)
    )).delete()

    await SessionManager.subscribe_to_channel(channel.id, [added_user.id for added_user in added_users])

    for added_user in added_users:
        await upd.update_channel_for_user(channel, added_user)

    return InvitedUsers(
        updates=Updates(
            updates=[UpdateChannel(channel_id=channel.make_id())],
            chats=[await channel.to_tl(user)],
            users=[],
            date=int(time()),
            seq=0,
        ),
        missing_invitees=[],
    )


@handler.on_request(ToggleSignatures, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def toggle_signatures(request: ToggleSignatures, user: User):
    peer = await Peer.from_input_peer_raise(
        user, request.channel, message="CHANNEL_PRIVATE", code=406, peer_types=(PeerType.CHANNEL,)
    )

    participant = await ChatParticipant.get_or_none(channel=peer.channel, user=user)
    if not peer.channel.admin_has_permission(participant, ChatAdminRights.CHANGE_INFO):
        raise ErrorRpc(error_code=403, error_message="CHAT_ADMIN_REQUIRED")

    channel = peer.channel
    if channel.signatures == request.signatures_enabled:
        raise ErrorRpc(error_code=400, error_message="CHAT_NOT_MODIFIED")

    channel.signatures = request.signatures_enabled
    channel.version += 1
    await channel.save(update_fields=["signatures", "version"])

    await AdminLogEntry.create(
        channel=peer.channel,
        user=user,
        action=AdminLogEntryAction.TOGGLE_SIGNATURES,
        prev=None,
        new=b"\x01" if request.signatures_enabled else b"\x00",
    )

    return await upd.update_channel(channel, user)


@handler.on_request(ToggleSignatures_133, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def toggle_signatures_136(request: ToggleSignatures_133, user: User):
    return await toggle_signatures(ToggleSignatures(
        signatures_enabled=request.enabled,
        profiles_enabled=False,
        channel=request.channel,
    ), user)


@handler.on_request(SetChatAvailableReactions_179, ReqHandlerFlags.BOT_NOT_ALLOWED)
@handler.on_request(SetChatAvailableReactions_145, ReqHandlerFlags.BOT_NOT_ALLOWED)
@handler.on_request(SetChatAvailableReactions_136, ReqHandlerFlags.BOT_NOT_ALLOWED)
@handler.on_request(SetChatAvailableReactions, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def set_chat_available_reactions(request: SetChatAvailableReactions, user: User) -> Updates:
    peer = await Peer.from_input_peer_raise(
        user, request.peer, message="CHANNEL_PRIVATE", code=406, peer_types=(PeerType.CHANNEL,)
    )

    channel = peer.channel

    participant = await ChatParticipant.get_or_none(channel=channel, user=user)
    if not channel.admin_has_permission(participant, ChatAdminRights.CHANGE_INFO):
        raise ErrorRpc(error_code=403, error_message="CHAT_ADMIN_REQUIRED")

    reactions = request.available_reactions
    if isinstance(reactions, ChatReactionsAll):
        if channel.all_reactions and reactions.allow_custom == channel.all_reactions_custom:
            raise ErrorRpc(error_code=400, error_message="CHAT_NOT_MODIFIED")

        channel.all_reactions = True
        channel.all_reactions_custom = reactions.allow_custom
    elif isinstance(reactions, ChatReactionsNone):
        some_available = await AvailableChannelReaction.filter(channel=channel).exists()
        if not channel.all_reactions and not some_available:
            raise ErrorRpc(error_code=400, error_message="CHAT_NOT_MODIFIED")

        channel.all_reactions = False
        await AvailableChannelReaction.filter(channel=channel).delete()
    elif isinstance(reactions, ChatReactionsSome):
        if not reactions.reactions:
            raise ErrorRpc(error_code=400, error_message="REACTION_INVALID")  # TODO: or set to ChatReactionsNone?

        reactions_emoticons = []

        for reaction in reactions.reactions:
            if isinstance(reaction, ReactionEmoji):
                reactions_emoticons.append(Reaction.reaction_to_uuid(reaction.emoticon))
            elif isinstance(reaction, ReactionCustomEmoji):
                raise ErrorRpc(error_code=400, error_message="REACTION_INVALID")

        new_reactions = await Reaction.filter(reaction_id__in=reactions_emoticons)
        current_reactions = dict(await AvailableChannelReaction.filter(
            channel=channel,
        ).values_list("reaction__id", "id"))

        to_create_reactions = []

        for reaction in new_reactions:
            if reaction.id not in current_reactions:
                to_create_reactions.append(AvailableChannelReaction(channel=channel, reaction=reaction))
            else:
                del current_reactions[reaction.id]

        to_delete_ids = list(current_reactions.values())

        if not to_create_reactions and not to_delete_ids:
            raise ErrorRpc(error_code=400, error_message="CHAT_NOT_MODIFIED")

        if to_create_reactions:
            await AvailableChannelReaction.bulk_create(to_create_reactions)
        if to_delete_ids:
            await AvailableChannelReaction.filter(id__in=to_delete_ids).delete()
    else:
        raise Unreachable

    channel.version += 1
    await channel.save(update_fields=["all_reactions", "all_reactions_custom", "version"])

    return await upd.update_channel(channel, user)


@handler.on_request(DeleteChannel, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def delete_channel(request: DeleteChannel, user: User) -> Updates:
    peer = await Peer.from_input_peer_raise(
        user, request.channel, message="CHANNEL_PRIVATE", code=406, peer_types=(PeerType.CHANNEL,)
    )

    channel = peer.channel

    if channel.creator_id != user.id:
        raise ErrorRpc(error_code=400, error_message="CHAT_ADMIN_REQUIRED")

    channel.deleted = True
    channel.version += 1
    await channel.save(update_fields=["deleted", "version"])

    await UserPersonalChannel.filter(channel=channel).delete()
    # TODO: delete channel peers, dialogs, participants and messages lazily or in background

    return await upd.update_channel(channel, user)


@handler.on_request(EditCreator, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def edit_creator(request: EditCreator, user: User) -> Updates:
    peer = await Peer.from_input_peer_raise(
        user, request.channel, message="CHANNEL_PRIVATE", code=406, peer_types=(PeerType.CHANNEL,)
    )

    channel = peer.channel
    if channel.creator_id != user.id:
        raise ErrorRpc(error_code=400, error_message="CHAT_ADMIN_REQUIRED")

    participant = await ChatParticipant.get_or_none(user=user, channel=channel)
    if participant is None:
        # what
        raise ErrorRpc(error_code=400, error_message="CHAT_ADMIN_REQUIRED")

    password = await UserPassword.get_or_none(user=user)
    if password is None or password.password is None:
        raise ErrorRpc(error_code=400, error_message="PASSWORD_MISSING")

    await check_password_internal(password, request.password)

    target_peer = await Peer.from_input_peer_raise(user, request.user_id)
    if target_peer.type is not PeerType.USER:
        raise ErrorRpc(error_code=400, error_message="USER_ID_INVALID")
    target_participant = await ChatParticipant.get_or_none(user=target_peer.user, channel=channel)
    if target_participant is None:
        raise ErrorRpc(error_code=400, error_message="USER_ID_INVALID")

    # TODO: do this in transaction

    channel.creator = target_peer.user
    await channel.save(update_fields=["creator_id"])

    participant.admin_rights = ChatAdminRights(0)
    target_participant.admin_rights = ChatAdminRights.from_tl(CREATOR_RIGHTS)
    await ChatParticipant.bulk_update([participant, target_participant], fields=["admin_rights"])

    return await upd.update_channel(channel, user, send_to_users=[user.id, target_peer.user.id])


@handler.on_request(JoinChannel, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def join_channel(request: JoinChannel, user: User) -> Updates:
    peer = await Peer.from_input_peer_raise(
        user, request.channel, message="CHANNEL_PRIVATE", code=406, peer_types=(PeerType.CHANNEL,)
    )

    if await ChatParticipant.filter(channel=peer.channel, user=user).exists():
        raise ErrorRpc(error_code=400, error_message="USER_ALREADY_PARTICIPANT")

    if not await Username.filter(channel=peer.channel).exists():
        raise ErrorRpc(error_code=406, error_message="CHANNEL_PRIVATE")

    return await user_join_chat_or_channel(peer.channel, user, None)


@handler.on_request(LeaveChannel)
async def leave_channel(request: LeaveChannel, user: User) -> Updates:
    peer = await Peer.from_input_peer_raise(
        user, request.channel, message="CHANNEL_PRIVATE", code=406, peer_types=(PeerType.CHANNEL,)
    )

    if peer.channel.creator_id == user.id:
        raise ErrorRpc(error_code=400, error_message="USER_CREATOR")

    participant = await ChatParticipant.get_or_none(channel=peer.channel, user=user)
    if participant is None:
        raise ErrorRpc(error_code=400, error_message="USER_NOT_PARTICIPANT")

    await participant.delete()
    await ChatInvite.filter(channel=peer.channel, user=user).update(revoked=True)
    await Dialog.hide(peer)
    await Message.filter(id__in=Subquery(
        Message.filter(
            peer__channel=peer.channel, peer__owner=user, type=MessageType.SCHEDULED,
        ).values_list("id", flat=True)
    )).delete()

    return await upd.update_channel_for_user(peer.channel, user)


@handler.on_request(GetAdminedPublicChannels, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def get_admined_public_channels(request: GetAdminedPublicChannels, user: User) -> Chats:
    query = Channel.filter(deleted=False, creator=user, chatparticipants__user=user, usernames__isnull=False)

    if request.check_limit and await query.count() >= AppConfig.PUBLIC_CHANNELS_LIMIT:
        raise ErrorRpc(error_code=400, error_message="CHANNELS_ADMIN_PUBLIC_TOO_MUCH")

    return Chats(chats=[
        await channel.to_tl(user)
        for channel in await query
    ])


@handler.on_request(TogglePreHistoryHidden, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def toggle_pre_history_hidden(request: TogglePreHistoryHidden, user: User) -> Updates:
    peer = await Peer.from_input_peer_raise(
        user, request.channel, message="CHANNEL_PRIVATE", code=406, peer_types=(PeerType.CHANNEL,)
    )

    channel = peer.channel

    if channel.is_discussion:
        # TODO: is this a correct error message?
        raise ErrorRpc(error_code=400, error_message="CHAT_LINK_EXISTS")

    if channel.hidden_prehistory == request.enabled:
        raise ErrorRpc(error_code=400, error_message="CHAT_NOT_MODIFIED")

    participant = await channel.get_participant_raise(user)
    if not channel.admin_has_permission(participant, ChatAdminRights.CHANGE_INFO):
        raise ErrorRpc(error_code=403, error_message="CHAT_ADMIN_REQUIRED")

    if await Username.filter(channel=channel).exists():
        raise ErrorRpc(error_code=400, error_message="CHAT_LINK_EXISTS")

    channel.min_available_id = cast(
        int | None,
        await Message.filter(
            peer__owner=None, peer__channel=channel,
        ).order_by("-id").first().values_list("id", flat=True)
    )
    if channel.min_available_id is not None:
        channel.min_available_id += 1
    channel.hidden_prehistory = request.enabled
    channel.version += 1
    await channel.save(update_fields=["hidden_prehistory", "min_available_id", "version"])

    return await upd.update_channel(channel, user)


@handler.on_request(ToggleJoinToSend, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def toggle_join_to_send(request: ToggleJoinToSend, user: User) -> Updates:
    peer = await Peer.from_input_peer_raise(
        user, request.channel, message="CHANNEL_PRIVATE", code=406, peer_types=(PeerType.CHANNEL,)
    )

    channel = peer.channel
    if not request.enabled and not channel.is_discussion:
        # As per https://core.telegram.org/constructor/channel,
        # "Whether a user needs to join the supergroup before they can send messages:
        # can be false only for discussion groups"
        raise ErrorRpc(error_code=400, error_message="CHANNEL_INVALID")

    if channel.join_to_send == request.enabled:
        raise ErrorRpc(error_code=400, error_message="CHAT_NOT_MODIFIED")

    participant = await channel.get_participant_raise(user)
    if not channel.admin_has_permission(participant, ChatAdminRights.CHANGE_INFO):
        raise ErrorRpc(error_code=403, error_message="CHAT_ADMIN_REQUIRED")

    channel.join_to_send = request.enabled
    channel.version += 1
    await channel.save(update_fields=["join_to_send", "version"])

    return await upd.update_channel(channel, user)


@handler.on_request(GetSendAs_135, ReqHandlerFlags.BOT_NOT_ALLOWED)
@handler.on_request(GetSendAs, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def get_send_as(request: GetSendAs | GetSendAs_135, user: User) -> SendAsPeers:
    peer = await Peer.from_input_peer_raise(
        user, request.peer, message="CHANNEL_PRIVATE", code=406, peer_types=(PeerType.CHANNEL,)
    )

    channel = peer.channel
    if not channel.supergroup:
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    if channel.creator_id != user.id:
        return SendAsPeers(
            peers=[SendAsPeer(peer=PeerUser(user_id=user.id))],
            chats=[],
            users=[await user.to_tl(user)],
        )

    return SendAsPeers(
        peers=[
            SendAsPeer(peer=PeerUser(user_id=user.id)),
            SendAsPeer(peer=PeerChannel(channel_id=channel.make_id())),
        ],
        chats=[await channel.to_tl(user)],
        users=[await user.to_tl(user)],
    )


@handler.on_request(GetAdminLog, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def get_admin_log(request: GetAdminLog, user: User) -> AdminLogResults:
    peer = await Peer.from_input_peer_raise(
        user, request.channel, message="CHANNEL_PRIVATE", code=406, peer_types=(PeerType.CHANNEL,)
    )

    channel = peer.channel

    participant = await channel.get_participant_raise(user)
    if not channel.admin_has_permission(participant, ChatAdminRights.CHANGE_INFO) \
            or not channel.admin_has_permission(participant, ChatAdminRights.OTHER):
        raise ErrorRpc(error_code=403, error_message="CHAT_ADMIN_REQUIRED")

    events_q = Q(channel=channel)

    if request.events_filter is not None:
        actions_q = Q()
        if request.events_filter.info:
            actions_q |= Q(action=AdminLogEntryAction.CHANGE_TITLE) \
                         | Q(action=AdminLogEntryAction.CHANGE_ABOUT) \
                         | Q(action=AdminLogEntryAction.CHANGE_USERNAME)

        if not actions_q.filters and not actions_q.children:
            return AdminLogResults(events=[], users=[], chats=[])

        events_q &= actions_q

    if request.admins:
        admin_ids = []
        for input_admin in request.admins:
            if isinstance(input_admin, InputUserSelf):
                admin_ids.append(user.id)
            elif isinstance(input_admin, (InputUser, InputUserFromMessage)):
                admin_ids.append(input_admin.user_id)

        if not admin_ids:
            return AdminLogResults(events=[], users=[], chats=[])

        events_q &= Q(user__id__in=admin_ids)

    if request.max_id:
        # TODO: or __le?
        events_q &= Q(id__lte=request.max_id)
    if request.min_id:
        # TODO: or __ge?
        events_q &= Q(id__gte=request.min_id)

    limit = max(1, min(100, request.limit))

    events = []
    users = {}

    for event in await AdminLogEntry.filter(events_q).limit(limit).select_related(
            "user", "old_photo", "new_photo",
    ):
        event_tl = event.to_tl()
        if event_tl is None:
            continue
        events.append(event_tl)
        if event.user_id not in users:
            users[event.user_id] = await event.user.to_tl(user)

    return AdminLogResults(
        events=events,
        users=list(users.values()),
        chats=[await channel.to_tl(user)],
    )


@handler.on_request(ToggleJoinRequest, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def toggle_join_request(request: ToggleJoinRequest, user: User) -> Updates:
    peer = await Peer.from_input_peer_raise(
        user, request.channel, message="CHANNEL_PRIVATE", code=406, peer_types=(PeerType.CHANNEL,)
    )

    channel = peer.channel

    if channel.join_request == request.enabled:
        raise ErrorRpc(error_code=400, error_message="CHAT_NOT_MODIFIED")

    participant = await channel.get_participant_raise(user)
    if not channel.admin_has_permission(participant, ChatAdminRights.CHANGE_INFO):
        raise ErrorRpc(error_code=403, error_message="CHAT_ADMIN_REQUIRED")

    channel.join_request = request.enabled
    channel.version += 1
    await channel.save(update_fields=["join_to_send", "version"])

    return await upd.update_channel(channel, user)


@handler.on_request(GetGroupsForDiscussion, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def get_groups_for_discussion(user: User) -> Chats:
    chats = await Chat.filter(creator=user, migrated=False).order_by("-id")
    channels = await Channel.filter(creator=user, supergroup=True).order_by("-id")

    return Chats(
        chats=[
            *await Channel.to_tl_bulk(channels, user),
            *await Chat.to_tl_bulk(chats, user),
        ],
    )


@handler.on_request(SetDiscussionGroup)
async def set_discussion_group(request: SetDiscussionGroup, user: User) -> bool:
    channel_peer = await Peer.from_input_peer_raise(
        user, request.broadcast, message="BROADCAST_ID_INVALID", code=400, peer_types=(PeerType.CHANNEL,)
    )
    channel = channel_peer.channel
    if channel.creator_id != user.id:
        raise ErrorRpc(error_code=400, error_message="CHAT_ADMIN_REQUIRED")

    group_peer = await Peer.from_input_peer_raise(
        user, request.group, message="MEGAGROUP_ID_INVALID", code=400, peer_types=(PeerType.CHANNEL,)
    )
    group = group_peer.channel
    if group.creator_id != user.id:
        raise ErrorRpc(error_code=400, error_message="CHAT_ADMIN_REQUIRED")

    if not group.supergroup or group.is_discussion:
        raise ErrorRpc(error_code=400, error_message="MEGAGROUP_ID_INVALID")
    if group.hidden_prehistory:
        raise ErrorRpc(error_code=400, error_message="MEGAGROUP_PREHISTORY_HIDDEN")

    if group.id == channel.discussion_id:
        raise ErrorRpc(error_code=400, error_message="CHANNEL_INVALID")

    channel.discussion = group
    group.is_discussion = True
    channel.version += 1
    group.version += 1

    async with in_transaction():
        await channel.save(update_fields=["discussion_id", "version"])
        await group.save(update_fields=["is_discussion", "version"])

    await upd.update_channel(channel, user)
    await upd.update_channel(group, user)

    return True

