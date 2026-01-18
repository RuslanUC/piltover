from datetime import datetime, UTC
from time import time
from typing import cast

from tortoise.expressions import Q, Subquery, RawSQL
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
    ChatInviteRequest, Username, ChatInvite, AvailableChannelReaction, Reaction, UserPassword, UserPersonalChannel, \
    Chat, PeerColorOption, File, SlowmodeLastMessage, AdminLogEntry, Contact
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
    InputUserFromMessage, PeerColor, InputPeerChannel, InputChannelEmpty, Int, ChannelParticipantsBots, \
    ChannelParticipantsContacts, ChannelParticipantsMentions, ChannelParticipantsBanned, ChannelParticipantsKicked, \
    ChannelParticipantLeft
from piltover.tl.functions.channels import GetChannelRecommendations, GetAdminedPublicChannels, CheckUsername, \
    CreateChannel, GetChannels, GetFullChannel, EditTitle, EditPhoto, GetMessages, DeleteMessages, EditBanned, \
    EditAdmin, GetParticipants, GetParticipant, ReadHistory, InviteToChannel, InviteToChannel_133, ToggleSignatures, \
    UpdateUsername, ToggleSignatures_133, GetMessages_40, DeleteChannel, EditCreator, JoinChannel, LeaveChannel, \
    TogglePreHistoryHidden, ToggleJoinToSend, GetSendAs, GetSendAs_135, GetAdminLog, ToggleJoinRequest, \
    GetGroupsForDiscussion, SetDiscussionGroup, UpdateColor, ToggleSlowMode, ToggleParticipantsHidden
from piltover.tl.functions.messages import SetChatAvailableReactions, SetChatAvailableReactions_136, \
    SetChatAvailableReactions_145, SetChatAvailableReactions_179
from piltover.tl.types.channels import ChannelParticipants, ChannelParticipant, SendAsPeers, AdminLogResults
from piltover.tl.types.messages import Chats, ChatFull as MessagesChatFull, Messages, AffectedMessages, InvitedUsers
from piltover.utils.users_chats_channels import UsersChatsChannels
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

    participant = await channel.get_participant(user)
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

    return Chats(
        chats=await Channel.to_tl_bulk(await Channel.filter(channels_q)),
    )


@handler.on_request(GetFullChannel)
async def get_full_channel(request: GetFullChannel, user: User) -> MessagesChatFull:
    peer = await Peer.from_input_peer_raise(
        user, request.channel, message="CHANNEL_PRIVATE", code=406, peer_types=(PeerType.CHANNEL,),
        select_related=("channel__discussion", "channel__photo",),
    )

    channel = peer.channel

    photo = PhotoEmpty(id=0)
    if channel.photo_id:
        photo = channel.photo.to_tl_photo()

    invite = None
    participant = await channel.get_participant(user, allow_left=True)
    if participant is not None \
            and not participant.left \
            and channel.admin_has_permission(participant, ChatAdminRights.INVITE_USERS):
        invite = await ChatInvite.get_or_create_permanent(user, channel)
    if participant is not None and participant.banned_rights & ChatBannedRights.VIEW_MESSAGES:
        raise ErrorRpc(error_code=406, error_message="CHANNEL_PRIVATE")

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

    channels_to_tl = [channel]

    linked_chat = None
    if channel.discussion_id:
        linked_chat = channel.discussion
    elif channel.is_discussion:
        linked_chat = await Channel.get_or_none(discussion=channel).select_related("photo")

    if linked_chat is not None:
        await Peer.get_or_create(owner=user, type=PeerType.CHANNEL, channel=linked_chat)
        channels_to_tl.append(linked_chat)

    slowmode_next_date = None
    if channel.slowmode_seconds:
        slowmode_last_date = cast(datetime | None, await SlowmodeLastMessage.get_or_none(
            channel=channel, user=user
        ).values_list("last_message", flat=True))
        if slowmode_last_date is not None:
            slowmode_next_date = int(slowmode_last_date.timestamp()) + channel.slowmode_seconds

    can_view_participants = not channel.participants_hidden
    if participant is not None and participant.is_admin:
        can_view_participants = True

    return MessagesChatFull(
        full_chat=ChannelFull(
            can_view_participants=can_view_participants,
            can_set_username=can_change_info,
            can_set_stickers=False,
            hidden_prehistory=channel.hidden_prehistory,
            can_set_location=False,
            has_scheduled=has_scheduled,
            can_view_stats=False,
            can_delete_channel=channel.creator_id == user.id,
            antispam=False,
            participants_hidden=channel.participants_hidden,
            translations_disabled=True,
            restricted_sponsored=True,
            can_view_revenue=False,

            id=channel.make_id(),
            about=channel.description,
            participants_count=await ChatParticipant.filter(channel=channel, left=False).count(),
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
                    peer__owner=None, peer__channel=channel, pinned=True,
                ).order_by("-id").first().values_list("id", flat=True)
            ),
            pts=channel.pts,
            exported_invite=await invite.to_tl() if invite is not None else None,
            available_reactions=available_reactions,
            ttl_period=channel.ttl_period_days * 86400 if channel.ttl_period_days else None,
            available_min_id=min_message_id,
            migrated_from_chat_id=Chat.make_id_from(migrated_from_chat_id) if migrated_from_chat_id else None,
            migrated_from_max_id=migrated_from_max_id,
            linked_chat_id=linked_chat.make_id() if linked_chat else None,
            slowmode_seconds=channel.slowmode_seconds,
            slowmode_next_send_date=slowmode_next_date,
        ),
        chats=await Channel.to_tl_bulk(channels_to_tl),
        users=[await user.to_tl(user)],
    )


@handler.on_request(EditTitle)
async def edit_channel_title(request: EditTitle, user: User) -> Updates:
    peer = await Peer.from_input_peer_raise(
        user, request.channel, message="CHANNEL_PRIVATE", code=406, peer_types=(PeerType.CHANNEL,)
    )

    participant = await peer.channel.get_participant(user)
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

    participant = await peer.channel.get_participant(user)
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

    return await format_messages_internal(user, await Message.filter(query).select_related(*Message.PREFETCH_FIELDS))


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
    channel = peer.channel
    participant = await channel.get_participant_raise(user)
    if not channel.admin_has_permission(participant, ChatAdminRights.BAN_USERS):
        raise ErrorRpc(error_code=403, error_message="RIGHT_FORBIDDEN")

    target_peer = await Peer.from_input_peer_raise(user, request.participant)
    if target_peer.type is not PeerType.USER:
        raise ErrorRpc(error_code=400, error_message="PARTICIPANT_ID_INVALID")
    target_participant = await channel.get_participant(target_peer.user, allow_left=True)

    new_banned_rights = ChatBannedRights.from_tl(request.banned_rights)
    banned_for = request.banned_rights.until_date - time()
    if not new_banned_rights or banned_for < 30 or banned_for > 86400 * 366:
        banned_until = datetime.fromtimestamp(0, UTC)
    else:
        banned_until = datetime.fromtimestamp(request.banned_rights.until_date, UTC)

    if target_participant is not None and target_participant.banned_rights == new_banned_rights:
        return Updates(updates=[], users=[], chats=[], date=int(time()), seq=0)

    # TODO: check if target_participant is not an admin

    was_participant = target_participant is not None and not target_participant.left
    left = (
            target_participant is None
            or target_participant.left
            or bool(new_banned_rights & ChatBannedRights.VIEW_MESSAGES)
    )

    participant_tl_before = ChannelParticipantLeft(peer=PeerUser(user_id=target_peer.user_id))
    if target_participant is not None:
        participant_tl_before = target_participant.to_tl_channel_with_creator(user, channel.creator_id)

    target_participant, created = await ChatParticipant.update_or_create(
        user=target_peer.user,
        channel=channel,
        defaults={
            "banned_rights": new_banned_rights,
            "banned_until": banned_until,
            "left": left,
            "inviter_id": 0,
            "invited_at": datetime.now(UTC),
        },
    )

    if new_banned_rights & ChatBannedRights.VIEW_MESSAGES:
        await ChatInviteRequest.filter(id__in=Subquery(
            ChatInviteRequest.filter(user=target_peer.user, invite__channel=channel).values_list("id", flat=True)
        ))

    await AdminLogEntry.create(
        channel=channel,
        user=user,
        action=AdminLogEntryAction.PARTICIPANT_BAN,
        prev=participant_tl_before.write(),
        new=target_participant.to_tl_channel_with_creator(user, channel.creator_id).write(),
    )

    if was_participant:
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
    creator_id = channel.creator_id

    participant = await channel.get_participant_raise(user)
    if not channel.admin_has_permission(participant, ChatAdminRights.ADD_ADMINS):
        raise ErrorRpc(error_code=403, error_message="RIGHT_FORBIDDEN")

    target_peer = await Peer.from_input_peer_raise(
        user, request.user_id, "PARTICIPANT_ID_INVALID", peer_types=(PeerType.USER, PeerType.SELF,)
    )
    if target_peer.user_id == creator_id and target_peer.user_id != user.id:
        raise ErrorRpc(error_code=400, error_message="USER_CREATOR")
    target_participant = await channel.get_participant(target_peer.user)
    if target_participant is None:
        raise ErrorRpc(error_code=400, error_message="PARTICIPANT_ID_INVALID")

    new_admin_rights = ChatAdminRights.from_tl(request.admin_rights)
    if target_peer.user_id == creator_id:
        new_admin_rights |= ChatAdminRights.from_tl(CREATOR_RIGHTS)

    if user.id != creator_id:
        if participant.admin_rights ^ new_admin_rights:
            raise ErrorRpc(error_code=403, error_message="RIGHT_FORBIDDEN")

    if target_participant.admin_rights == new_admin_rights and target_participant.admin_rank == request.rank:
        return Updates(updates=[], users=[], chats=[], date=int(time()), seq=0)

    participant_tl_before = target_participant.to_tl_channel_with_creator(user, creator_id)

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

    await AdminLogEntry.create(
        channel=channel,
        user=user,
        action=AdminLogEntryAction.PARTICIPANT_ADMIN,
        prev=participant_tl_before.write(),
        new=target_participant.to_tl_channel_with_creator(user, creator_id).write(),
    )

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

    this_participant = await peer.channel.get_participant(user)
    if peer.channel.participants_hidden and (this_participant is None or not this_participant.is_admin):
        raise ErrorRpc(error_code=403, error_message="CHAT_ADMIN_REQUIRED")

    filt = request.filter

    view_value = ChatBannedRights.VIEW_MESSAGES.value
    query = ChatParticipant.filter(channel=peer.channel)
    if this_participant is None or not this_participant.is_admin or isinstance(filt, ChannelParticipantsMentions):
        anon_value = ChatAdminRights.ANONYMOUS.value
        query = query.annotate(check_anon=RawSQL(f"admin_rights & {anon_value}")).filter(check_anon=0)

    if isinstance(filt, ChannelParticipantsRecent):
        query = query.order_by("-invited_at")
    elif isinstance(filt, ChannelParticipantsAdmins):
        query = query.filter(admin_rights__gt=0).order_by("user__id")
    elif isinstance(filt, ChannelParticipantsSearch):
        ...  # Handled below
    elif isinstance(filt, ChannelParticipantsBots):
        query = query.filter(user__bot=True).order_by("user__id")
    elif isinstance(filt, ChannelParticipantsContacts):
        query = query.filter(user__id__in=Subquery(Contact.filter(owner=user).values_list("target__id", flat=True)))
    elif isinstance(filt, ChannelParticipantsMentions):
        if filt.top_msg_id:
            query = query.filter(user__id__in=Subquery(
                Message.filter(
                    peer__owner=None, peer__channel=peer.channel, reply_to__id=filt.top_msg_id,
                ).distinct().values_list("author__id", flat=True)
            ))
    elif isinstance(filt, ChannelParticipantsBanned):
        query = query.annotate(
            check_view_banned=RawSQL(f"banned_rights & {view_value}"),
        ).filter(banned_rights__gt=0, check_view_banned=0)
    elif isinstance(filt, ChannelParticipantsKicked):
        query = query.annotate(
            check_view_banned=RawSQL(f"banned_rights & {view_value}"),
        ).filter(check_view_banned__not=0)
    else:
        raise Unreachable

    if isinstance(filt, (
            ChannelParticipantsSearch, ChannelParticipantsContacts, ChannelParticipantsMentions,
            ChannelParticipantsBanned, ChannelParticipantsKicked,
    )):
        if filt.q:
            query = query.filter(Q(
                user__first_name__icontains=filt.q,
                user__usernames__username__icontains=filt.q,
            ))
        query = query.order_by("user__id")

    limit = max(min(request.limit, 100), 1)
    participants = await query.select_related("user").limit(limit).offset(request.offset)

    participants_tl = []
    users_to_tl = []

    peers_to_create = []

    for participant in participants:
        if participant.user != user:
            peers_to_create.append(Peer(owner=user, user=participant.user, type=PeerType.USER))

    await Peer.bulk_create(peers_to_create, ignore_conflicts=True)

    for participant in participants:
        participants_tl.append(participant.to_tl_channel_with_creator(user, creator_id=peer.channel.creator_id))
        users_to_tl.append(participant.user)

    return ChannelParticipants(
        count=await query.count(),
        participants=participants_tl,
        chats=[await peer.channel.to_tl(user)],
        users=await User.to_tl_bulk(users_to_tl, user),
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
    participants_to_update = []

    for input_user in request.users[:100]:
        user_peer = await Peer.from_input_peer_raise(user, input_user)
        if user_peer.type is not PeerType.USER:
            raise ErrorRpc(error_code=400, error_message="USER_ID_INVALID")
        existing_participant = await ChatParticipant.get_or_none(user=user_peer.user, channel=channel)
        if existing_participant and not existing_participant.left:
            continue
        # TODO: use has_access_to_bulk
        if not await PrivacyRule.has_access_to(user, user_peer.user, PrivacyRuleKeyType.CHAT_INVITE):
            raise ErrorRpc(error_code=403, error_message="USER_PRIVACY_RESTRICTED")

        added_users.append(user_peer.user)
        peers_to_create.append(Peer(owner=user_peer.user, channel=channel, type=PeerType.CHANNEL))
        if existing_participant is None:
            participants_to_create.append(ChatParticipant(
                user=user_peer.user, channel=channel, inviter_id=user.id, min_message_id=channel.min_available_id,
            ))
        else:
            existing_participant.left = False
            participants_to_update.append(existing_participant)

    await Peer.bulk_create(peers_to_create, ignore_conflicts=True)
    if participants_to_create:
        await ChatParticipant.bulk_create(participants_to_create, ignore_conflicts=True)
    if participants_to_update:
        await ChatParticipant.bulk_update(participants_to_update, fields=["left"])
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

    participant = await peer.channel.get_participant(user)
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

    participant = await channel.get_participant(user)
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


async def _unlink_channel_maybe(channel: Channel) -> None:
    if channel.is_discussion:
        await Channel.filter(discussion=channel).update(discussion=None)
    elif channel.discussion_id:
        await Channel.filter(id=channel.discussion_id).update(is_discussion=False)


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
    await _unlink_channel_maybe(channel)
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

    participant = await channel.get_participant(user)
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
    target_participant = await channel.get_participant(target_peer.user)
    if target_participant is None:
        raise ErrorRpc(error_code=400, error_message="USER_ID_INVALID")

    async with in_transaction():
        channel.creator = target_peer.user
        await channel.save(update_fields=["creator_id"])

        participant.admin_rights = ChatAdminRights(0)
        target_participant.admin_rights = ChatAdminRights.from_tl(CREATOR_RIGHTS)
        await ChatParticipant.bulk_update([participant, target_participant], fields=["admin_rights"])

        await _unlink_channel_maybe(channel)

    return await upd.update_channel(channel, user, send_to_users=[user.id, target_peer.user.id])


@handler.on_request(JoinChannel, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def join_channel(request: JoinChannel, user: User) -> Updates:
    peer = await Peer.from_input_peer_raise(
        user, request.channel, message="CHANNEL_PRIVATE", code=406, peer_types=(PeerType.CHANNEL,)
    )

    participant = await ChatParticipant.get_or_none(channel=peer.channel, user=user)
    if participant is not None:
        if not participant.left:
            raise ErrorRpc(error_code=400, error_message="USER_ALREADY_PARTICIPANT")
        if participant.banned_rights & ChatBannedRights.VIEW_MESSAGES:
            raise ErrorRpc(error_code=406, error_message="CHANNEL_PRIVATE")

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

    participant = await peer.channel.get_participant(user)
    if participant is None:
        raise ErrorRpc(error_code=400, error_message="USER_NOT_PARTICIPANT")

    async with in_transaction():
        participant.left = True
        await participant.save(update_fields=["left"])
        await ChatInvite.filter(channel=peer.channel, user=user).update(revoked=True)
        await Dialog.hide(peer)
        await Message.filter(id__in=Subquery(
            Message.filter(
                peer__channel=peer.channel, peer__owner=user, type=MessageType.SCHEDULED,
            ).values_list("id", flat=True)
        )).delete()
        await AdminLogEntry.create(
            channel=peer.channel,
            user=user,
            action=AdminLogEntryAction.PARTICIPANT_LEAVE,
        )

    return await upd.update_channel_for_user(peer.channel, user)


@handler.on_request(GetAdminedPublicChannels, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def get_admined_public_channels(request: GetAdminedPublicChannels, user: User) -> Chats:
    query = Channel.filter(deleted=False, creator=user, chatparticipants__user=user, usernames__isnull=False)

    if request.check_limit and await query.count() >= AppConfig.PUBLIC_CHANNELS_LIMIT:
        raise ErrorRpc(error_code=400, error_message="CHANNELS_ADMIN_PUBLIC_TOO_MUCH")

    return Chats(
        chats=await Channel.to_tl_bulk(await query),
    )


@handler.on_request(TogglePreHistoryHidden, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def toggle_pre_history_hidden(request: TogglePreHistoryHidden, user: User) -> Updates:
    peer = await Peer.from_input_peer_raise(
        user, request.channel, message="CHANNEL_PRIVATE", code=406, peer_types=(PeerType.CHANNEL,)
    )

    channel = peer.channel

    if channel.is_discussion:
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
    await AdminLogEntry.create(
        channel=channel,
        user=user,
        action=AdminLogEntryAction.PREHISTORY_HIDDEN,
        new=b"\x01" if request.enabled else b"\x00"
    )

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
            peers=[SendAsPeer(peer=user.to_tl_peer())],
            chats=[],
            users=[await user.to_tl(user)],
        )

    return SendAsPeers(
        peers=[
            SendAsPeer(peer=user.to_tl_peer()),
            SendAsPeer(peer=channel.to_tl_peer()),
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
                         | Q(action=AdminLogEntryAction.CHANGE_USERNAME) \
                         | Q(action=AdminLogEntryAction.CHANGE_PHOTO) \
                         | Q(action=AdminLogEntryAction.EDIT_PEER_COLOR) \
                         | Q(action=AdminLogEntryAction.EDIT_PEER_COLOR_PROFILE) \
                         | Q(action=AdminLogEntryAction.LINKED_CHAT) \
                         | Q(action=AdminLogEntryAction.EDIT_HISTORY_TTL) \
                         | Q(action=AdminLogEntryAction.TOGGLE_SLOWMODE)
        if request.events_filter.join:
            actions_q |= Q(action=AdminLogEntryAction.PARTICIPANT_JOIN)
        if request.events_filter.leave:
            actions_q |= Q(action=AdminLogEntryAction.PARTICIPANT_LEAVE)
        if request.events_filter.settings:
            actions_q |= Q(action=AdminLogEntryAction.TOGGLE_SIGNATURES) \
                         | Q(action=AdminLogEntryAction.TOGGLE_NOFORWARDS) \
                         | Q(action=AdminLogEntryAction.DEFAULT_BANNED_RIGHTS) \
                         | Q(action=AdminLogEntryAction.PREHISTORY_HIDDEN)
        if request.events_filter.promote or request.events_filter.demote:
            actions_q |= Q(action=AdminLogEntryAction.PARTICIPANT_ADMIN)
        if request.events_filter.ban or request.events_filter.unban:
            actions_q |= Q(action=AdminLogEntryAction.PARTICIPANT_BAN)

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

    # TODO: or __le/__ge?
    if request.max_id:
        events_q &= Q(id__lte=request.max_id)
    if request.min_id:
        events_q &= Q(id__gte=request.min_id)

    limit = max(1, min(100, request.limit))

    events = []
    ucc = UsersChatsChannels()

    for event in await AdminLogEntry.filter(events_q).limit(limit).order_by("-id").select_related(
            "user", "old_photo", "new_photo",
    ):
        if (event_tl := event.to_tl(ucc)) is None:
            continue
        events.append(event_tl)

    users, chats, channels = await ucc.resolve(user)

    return AdminLogResults(
        events=events,
        users=users,
        chats=[*chats, *channels],
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
    channels = await Channel.filter(creator=user, supergroup=True, is_discussion=False).order_by("-id")

    return Chats(
        chats=[
            *await Channel.to_tl_bulk(channels),
            *await Chat.to_tl_bulk(chats),
        ],
    )


@handler.on_request(SetDiscussionGroup)
async def set_discussion_group(request: SetDiscussionGroup, user: User) -> bool:
    channel_peer = await Peer.from_input_peer_raise(
        user, request.broadcast, message="BROADCAST_ID_INVALID", code=400, peer_types=(PeerType.CHANNEL,),
        select_related=("channel__discussion",),
    )
    channel = channel_peer.channel
    if channel.creator_id != user.id:
        raise ErrorRpc(error_code=400, error_message="CHAT_ADMIN_REQUIRED")

    if isinstance(request.group, (InputChannel, InputPeerChannel)):
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
            raise ErrorRpc(error_code=400, error_message="MEGAGROUP_ID_INVALID")
    elif isinstance(request.group, InputChannelEmpty):
        group = None
    else:
        raise ErrorRpc(error_code=400, error_message="MEGAGROUP_ID_INVALID")

    if channel.discussion is None and group is None:
        raise ErrorRpc(error_code=400, error_message="LINK_NOT_MODIFIED")
    if group is not None and channel.discussion_id == group.id:
        raise ErrorRpc(error_code=400, error_message="LINK_NOT_MODIFIED")

    old_group = channel.discussion
    channel.discussion = group
    channel.version += 1
    if old_group is not None:
        old_group.is_discussion = False
        old_group.version += 1
    if group is not None:
        group.is_discussion = True
        group.version += 1

    channels_to_update = [channel]
    if old_group is not None:
        channels_to_update.append(old_group)
    if group is not None:
        channels_to_update.append(group)

    admin_log_to_create = [
        AdminLogEntry(
            channel=channel,
            user=user,
            action=AdminLogEntryAction.LINKED_CHAT,
            old_channel=old_group,
            new_channel=group,
        )
    ]
    if old_group is not None:
        admin_log_to_create.append(AdminLogEntry(
            channel=old_group,
            user=user,
            action=AdminLogEntryAction.LINKED_CHAT,
            old_channel=channel,
            new_channel=None,
        ))
    if group is not None:
        admin_log_to_create.append(AdminLogEntry(
            channel=group,
            user=user,
            action=AdminLogEntryAction.LINKED_CHAT,
            old_channel=None,
            new_channel=channel,
        ))

    async with in_transaction():
        await Channel.bulk_update(channels_to_update, fields=["discussion_id", "is_discussion", "version"])
        await AdminLogEntry.bulk_create(admin_log_to_create)

    await upd.update_channel(channel, user)
    if old_group is not None:
        await upd.update_channel(old_group, user)
    if group is not None:
        await upd.update_channel(group, user)

    return True


@handler.on_request(UpdateColor, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def update_color(request: UpdateColor, user: User) -> Updates:
    peer = await Peer.from_input_peer_raise(
        user, request.channel, message="CHANNEL_PRIVATE", code=406, peer_types=(PeerType.CHANNEL,),
    )

    channel = peer.channel
    participant = await channel.get_participant_raise(user)
    if not channel.admin_has_permission(participant, ChatAdminRights.CHANGE_INFO):
        raise ErrorRpc(error_code=403, error_message="CHAT_ADMIN_REQUIRED")

    changed = []

    old_color = channel.profile_color_id if request.for_profile else channel.accent_color_id
    old_emoji = channel.profile_emoji_id if request.for_profile else channel.accent_emoji_id
    new_color = old_color
    new_emoji = old_emoji

    if request.color is None and request.for_profile and channel.profile_color_id is not None:
        channel.profile_color = new_color = None
        changed.append("profile_color_id")
    elif request.color is None and not request.for_profile and channel.accent_color_id is not None:
        channel.accent_color = new_color = None
        changed.append("accent_color_id")
    elif request.color is not None:
        if (peer_color := await PeerColorOption.get_or_none(id=request.color, is_profile=request.for_profile)) is None:
            raise ErrorRpc(error_code=400, error_message="COLOR_INVALID")
        new_color = peer_color.id
        if request.for_profile:
            channel.profile_color = peer_color
            changed.append("profile_color_id")
        else:
            channel.accent_color = peer_color
            changed.append("accent_color_id")

    if request.background_emoji_id is None and request.for_profile and channel.profile_emoji_id is not None:
        channel.profile_emoji = new_emoji = None
        changed.append("profile_emoji_id")
    elif request.background_emoji_id is None and not request.for_profile and channel.accent_emoji_id is not None:
        channel.accent_emoji = new_emoji = None
        changed.append("accent_emoji_id")
    elif request.background_emoji_id is not None:
        emoji = await File.get_or_none(
            id=request.background_emoji_id, stickerset__installedstickersets__user=user,
        )
        if emoji is None:
            raise ErrorRpc(error_code=400, error_message="DOCUMENT_INVALID")
        new_emoji = emoji.id
        if request.for_profile:
            channel.profile_emoji = emoji
            changed.append("profile_emoji_id")
        else:
            channel.accent_emoji = emoji
            changed.append("accent_emoji_id")

    if not changed:
        raise ErrorRpc(error_code=400, error_message="CHANNEL_NOT_MODIFIED")

    await channel.save(update_fields=changed)

    if request.for_profile:
        action = AdminLogEntryAction.EDIT_PEER_COLOR_PROFILE
    else:
        action = AdminLogEntryAction.EDIT_PEER_COLOR
    await AdminLogEntry.create(
        channel=peer.channel,
        user=user,
        action=action,
        prev=PeerColor(color=old_color, background_emoji_id=old_emoji).serialize(),
        new=PeerColor(color=new_color, background_emoji_id=new_emoji).serialize(),
    )

    return await upd.update_channel(channel, user)


@handler.on_request(ToggleSlowMode, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def toggle_slowmode(request: ToggleSlowMode, user: User) -> Updates:
    peer = await Peer.from_input_peer_raise(
        user, request.channel, message="CHANNEL_PRIVATE", code=406, peer_types=(PeerType.CHANNEL,)
    )

    channel = peer.channel

    new_seconds = request.seconds or None
    if channel.slowmode_seconds == request.seconds:
        raise ErrorRpc(error_code=400, error_message="CHAT_NOT_MODIFIED")
    if new_seconds % 60 != 0 or new_seconds < 0 or new_seconds > 60 * 60:
        raise ErrorRpc(error_code=400, error_message="SECONDS_INVALID")

    participant = await channel.get_participant_raise(user)
    if not channel.admin_has_permission(participant, ChatAdminRights.CHANGE_INFO):
        raise ErrorRpc(error_code=403, error_message="CHAT_ADMIN_REQUIRED")

    old_seconds = channel.slowmode_seconds
    channel.slowmode_seconds = new_seconds
    channel.version += 1
    await channel.save(update_fields=["slowmode_seconds", "version"])

    await AdminLogEntry.create(
        channel=peer.channel,
        user=user,
        action=AdminLogEntryAction.TOGGLE_SLOWMODE,
        prev=Int.write(old_seconds or 0),
        new=Int.write(new_seconds or 0),
    )

    return await upd.update_channel(channel, user)


@handler.on_request(ToggleParticipantsHidden, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def toggle_participants_hidden(request: ToggleParticipantsHidden, user: User) -> Updates:
    peer = await Peer.from_input_peer_raise(
        user, request.channel, message="CHANNEL_PRIVATE", code=406, peer_types=(PeerType.CHANNEL,)
    )

    channel = peer.channel

    if channel.participants_hidden == request.enabled:
        raise ErrorRpc(error_code=400, error_message="CHAT_NOT_MODIFIED")

    participant = await channel.get_participant_raise(user)
    if not channel.admin_has_permission(participant, ChatAdminRights.CHANGE_INFO):
        raise ErrorRpc(error_code=403, error_message="CHAT_ADMIN_REQUIRED")

    channel.participants_hidden = request.enabled
    channel.version += 1
    await channel.save(update_fields=["participants_hidden", "version"])

    return await upd.update_channel(channel, user)
