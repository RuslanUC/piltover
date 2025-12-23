from datetime import datetime, UTC, timedelta
from typing import cast

from tortoise.expressions import Subquery, F
from tortoise.transactions import in_transaction

import piltover.app.utils.updates_manager as upd
from piltover.app.handlers.messages.sending import send_message_internal
from piltover.app_config import AppConfig
from piltover.context import request_ctx
from piltover.db.enums import PeerType, MessageType, PrivacyRuleKeyType, ChatBannedRights, ChatAdminRights, FileType, \
    UserStatus, AdminLogEntryAction
from piltover.db.models import User, Peer, Chat, File, UploadingFile, ChatParticipant, Message, PrivacyRule, \
    ChatInviteRequest, ChatInvite, Channel, Dialog, Presence, AdminLogEntry
from piltover.db.models.channel import CREATOR_RIGHTS
from piltover.enums import ReqHandlerFlags
from piltover.exceptions import ErrorRpc, Unreachable
from piltover.session_manager import SessionManager
from piltover.tl import MissingInvitee, InputUserFromMessage, InputUser, Updates, ChatFull, PeerNotifySettings, \
    ChatParticipants, InputChatPhotoEmpty, InputChatPhoto, InputChatUploadedPhoto, PhotoEmpty, InputPeerUser, \
    MessageActionChatCreate, MessageActionChatEditTitle, MessageActionChatAddUser, \
    MessageActionChatDeleteUser, MessageActionChatMigrateTo, MessageActionChannelMigrateFrom, ChatOnlines, \
    MessageActionChatEditPhoto
from piltover.tl.functions.messages import CreateChat, GetChats, CreateChat_150, GetFullChat, EditChatTitle, \
    EditChatAbout, EditChatPhoto, AddChatUser, DeleteChatUser, AddChatUser_133, EditChatAdmin, ToggleNoForwards, \
    EditChatDefaultBannedRights, CreateChat_133, MigrateChat, GetOnlines
from piltover.tl.types.messages import InvitedUsers, Chats, ChatFull as MessagesChatFull
from piltover.worker import MessageHandler

handler = MessageHandler("messages.chats")


@handler.on_request(CreateChat_133, ReqHandlerFlags.BOT_NOT_ALLOWED)
@handler.on_request(CreateChat_150, ReqHandlerFlags.BOT_NOT_ALLOWED)
@handler.on_request(CreateChat, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def create_chat(request: CreateChat, user: User) -> InvitedUsers:
    chat = await Chat.create(name=request.title, creator=user, participants_count=0)
    chat_peers = {user.id: await Peer.create(owner=user, chat=chat, type=PeerType.CHAT)}

    participants_to_create = [
        ChatParticipant(user=user, chat=chat, admin_rights=ChatAdminRights.from_tl(CREATOR_RIGHTS))
    ]

    missing = []
    # TODO: do it in one query (instead of calling Peer.from_input_peer every iteration)
    for invited_user in request.users:
        if not isinstance(invited_user, (InputUser, InputUserFromMessage, InputPeerUser)):
            continue
        if invited_user.user_id in chat_peers:
            continue

        try:
            invited_peer = await Peer.from_input_peer(user, invited_user)
        except ErrorRpc:
            continue
        if invited_peer is None:
            if isinstance(invited_user, (InputUser, InputUserFromMessage)):
                missing.append(MissingInvitee(user_id=invited_user.user_id))
            continue

        chat_peers[invited_peer.user.id] = await Peer.create(owner=invited_peer.user, chat=chat, type=PeerType.CHAT)
        participants_to_create.append(ChatParticipant(user=invited_peer.user, chat=chat, inviter_id=user.id))

    async with in_transaction():
        # TODO: also create peers in here
        await ChatParticipant.bulk_create(participants_to_create)
        chat.participants_count = len(participants_to_create)
        await chat.save(update_fields=["participants_count"])

    updates = await upd.create_chat(user, chat, list(chat_peers.values()))
    updates_msg = await send_message_internal(
        user, chat_peers[user.id], None, None, False,
        author=user, type=MessageType.SERVICE_CHAT_CREATE,
        extra_info=MessageActionChatCreate(title=request.title, users=list(chat_peers.keys())).write(),
    )

    if isinstance(updates_msg, Updates):
        updates.updates.extend(updates_msg.updates)

    return InvitedUsers(
        updates=updates,
        missing_invitees=missing,
    )


@handler.on_request(GetChats)
async def get_chats(request: GetChats, user: User) -> Chats:
    chat_ids = [Chat.norm_id(chat_id) for chat_id in request.id]
    peers = await Peer.filter(owner=user, chat__id__in=chat_ids).select_related("chat")

    return Chats(
        chats=[
            await peer.chat.to_tl(user)
            for peer in peers
        ],
    )


@handler.on_request(GetFullChat)
async def get_full_chat(request: GetFullChat, user: User) -> MessagesChatFull:
    peer = await Peer.from_chat_id_raise(user, request.chat_id, allow_migrated=True)

    chat = peer.chat
    photo = PhotoEmpty(id=0)
    if chat.photo_id:
        await chat.fetch_related("photo")
        photo = chat.photo.to_tl_photo()

    invite = None
    participant = await ChatParticipant.get_or_none(chat=chat, user=user)
    if chat.admin_has_permission(participant, ChatAdminRights.INVITE_USERS):
        invite = await ChatInvite.get_or_create_permanent(user, peer.chat_or_channel)

    return MessagesChatFull(
        full_chat=ChatFull(
            can_set_username=True,
            translations_disabled=True,
            id=chat.make_id(),
            about=chat.description,
            participants=ChatParticipants(
                chat_id=chat.make_id(),
                participants=[
                    await participant.to_tl(chat.creator_id)
                    for participant in await ChatParticipant.filter(chat=chat)
                ],
                version=chat.version,
            ),
            notify_settings=PeerNotifySettings(),
            chat_photo=photo,
            ttl_period=chat.ttl_period_days * 86400 if chat.ttl_period_days else None,
            exported_invite=await invite.to_tl() if invite is not None else None,
        ),
        chats=[await chat.to_tl(user)],
        users=[await user.to_tl(user)],
    )


@handler.on_request(EditChatTitle)
async def edit_chat_title(request: EditChatTitle, user: User) -> Updates:
    peer = await Peer.from_chat_id_raise(user, request.chat_id)

    participant = await ChatParticipant.get_or_none(chat=peer.chat, user=user)
    if participant is None or not (participant.is_admin or peer.chat.creator_id == user.id):
        raise ErrorRpc(error_code=400, error_message="CHAT_ADMIN_REQUIRED")

    await peer.chat.update(title=request.title)
    return await send_message_internal(
        user, peer, None, None, False,
        author=user, type=MessageType.SERVICE_CHAT_EDIT_TITLE,
        extra_info=MessageActionChatEditTitle(title=request.title).write(),
    )


@handler.on_request(EditChatAbout)
async def edit_chat_about(request: EditChatAbout, user: User) -> bool:
    peer = await Peer.from_input_peer_raise(user, request.peer, peer_types=(PeerType.CHAT, PeerType.CHANNEL))

    participant = await ChatParticipant.get_or_none(**Chat.or_channel(peer.chat_or_channel), user=user)
    if participant is None or not (participant.is_admin or peer.chat_or_channel.creator_id == user.id):
        raise ErrorRpc(error_code=400, error_message="CHAT_ADMIN_REQUIRED")

    chat_or_channel = peer.chat_or_channel
    old_about = chat_or_channel.description
    await chat_or_channel.update(description=request.about)

    if isinstance(chat_or_channel, Chat):
        await upd.update_chat(chat_or_channel)
    elif isinstance(chat_or_channel, Channel):
        await AdminLogEntry.create(
            channel=peer.channel,
            user=user,
            action=AdminLogEntryAction.CHANGE_ABOUT,
            prev=old_about.encode("utf8"),
            new=chat_or_channel.description.encode("utf8"),
        )
        await upd.update_channel(chat_or_channel, user)
    else:
        raise Unreachable

    return True


async def resolve_input_chat_photo(
        user: User, photo: InputChatPhotoEmpty | InputChatPhoto | InputChatUploadedPhoto,
) -> File | None:
    if isinstance(photo, InputChatPhotoEmpty):
        return None
    elif isinstance(photo, InputChatPhoto):
        if not await Peer.filter(owner=user, chat__photo__id=photo.id).exists():
            raise ErrorRpc(error_code=400, error_message="PHOTO_INVALID")
        return await File.get_or_none(id=photo.id)
    elif isinstance(photo, InputChatUploadedPhoto):
        if photo.file is None:
            raise ErrorRpc(error_code=400, error_message="PHOTO_FILE_MISSING")
        uploaded_file = await UploadingFile.get_or_none(user=user, file_id=photo.file.id)
        if uploaded_file is None:
            raise ErrorRpc(error_code=400, error_message="INPUT_FILE_INVALID")
        if uploaded_file.mime is None or not uploaded_file.mime.startswith("image/"):
            raise ErrorRpc(error_code=400, error_message="INPUT_FILE_INVALID")

        storage = request_ctx.get().storage
        file = await uploaded_file.finalize_upload(
            storage, "image/png", file_type=FileType.PHOTO, profile_photo=True,
        )

        return file

    raise ErrorRpc(error_code=400, error_message="CHAT_NOT_MODIFIED")


@handler.on_request(EditChatPhoto)
async def edit_chat_photo(request: EditChatPhoto, user: User):
    peer = await Peer.from_chat_id_raise(user, request.chat_id)

    participant = await ChatParticipant.get_or_none(chat=peer.chat, user=user)
    if participant is None or not (participant.is_admin or peer.chat.creator_id == user.id):
        raise ErrorRpc(error_code=400, error_message="CHAT_ADMIN_REQUIRED")

    chat = peer.chat
    await chat.update(photo=await resolve_input_chat_photo(user, request.photo))

    return await send_message_internal(
        user, peer, None, None, False,
        author=user, type=MessageType.SERVICE_CHAT_EDIT_PHOTO,
        extra_info=MessageActionChatEditPhoto(
            photo=chat.photo.to_tl_photo() if chat.photo else PhotoEmpty(id=0),
        ).write(),
    )


@handler.on_request(AddChatUser_133, ReqHandlerFlags.BOT_NOT_ALLOWED)
@handler.on_request(AddChatUser, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def add_chat_user(request: AddChatUser, user: User):
    chat_peer = await Peer.from_chat_id_raise(user, request.chat_id)
    user_peer = await Peer.from_input_peer_raise(user, request.user_id)

    participant = await chat_peer.chat.get_participant_raise(user)
    if not chat_peer.chat.user_has_permission(participant, ChatBannedRights.INVITE_USERS):
        raise ErrorRpc(error_code=403, error_message="CHAT_WRITE_FORBIDDEN")

    if await Peer.filter(owner=user_peer.user, chat=chat_peer.chat).exists():
        raise ErrorRpc(error_code=400, error_message="USER_ALREADY_PARTICIPANT")

    if await ChatParticipant.filter(chat=chat_peer.chat).count() > AppConfig.BASIC_GROUP_MEMBER_LIMIT:
        raise ErrorRpc(error_code=400, error_message="USERS_TOO_MUCH")

    if not await PrivacyRule.has_access_to(user, user_peer.user, PrivacyRuleKeyType.CHAT_INVITE):
        raise ErrorRpc(error_code=403, error_message="USER_PRIVACY_RESTRICTED")

    chat_peers = {
        peer.owner.id: peer
        for peer in await Peer.filter(chat=chat_peer.chat).select_related("owner", "chat")
    }
    if chat_peer.owner.id not in chat_peers:
        chat_peers[chat_peer.owner.id] = chat_peer
    invited_user = user_peer.peer_user(user)
    if user_peer.peer_user(user).id not in chat_peers:
        async with in_transaction():
            chat_peers[invited_user.id] = await Peer.create(owner=invited_user, chat=chat_peer.chat, type=PeerType.CHAT)
            await ChatParticipant.create(user=invited_user, chat=chat_peer.chat, inviter_id=user.id)
            await ChatInviteRequest.filter(id__in=Subquery(
                ChatInviteRequest.filter(user=invited_user, invite__chat=chat_peer.chat).values_list("id", flat=True)
            )).delete()
            await Chat.filter(id=chat_peer.chat_id).update(participants_count=F("participants_count") + 1)

    updates = await upd.create_chat(user, chat_peer.chat, list(chat_peers.values()))

    if request.fwd_limit > 0:
        limit = min(request.fwd_limit, 100)
        messages_to_forward = await Message.filter(
            peer=chat_peer, type=MessageType.REGULAR
        ).order_by("-id").limit(limit).select_related("author", "media", "reply_to", "fwd_header")
        messages = []
        for message in reversed(messages_to_forward):
            messages.append(await message.clone_for_peer(
                chat_peers[invited_user.id], internal_id=message.internal_id, media_group_id=message.media_group_id,
            ))

        await upd.send_messages({chat_peers[invited_user.id]: messages})

    updates_msg = await send_message_internal(
        user, chat_peers[user.id], None, None, False,
        author=user, type=MessageType.SERVICE_CHAT_USER_ADD,
        extra_info=MessageActionChatAddUser(users=[invited_user.id]).write(),
    )

    if isinstance(updates_msg, Updates):
        updates.updates.extend(updates_msg.updates)

    return InvitedUsers(
        updates=updates,
        missing_invitees=[],
    )


@handler.on_request(DeleteChatUser)
async def delete_chat_user(request: DeleteChatUser, user: User):
    chat_peer = await Peer.from_chat_id_raise(user, request.chat_id)
    user_peer = await Peer.from_input_peer_raise(user, request.user_id)

    participant = await ChatParticipant.get_or_none(chat=chat_peer.chat, user=user)
    if participant is None or not (participant.is_admin or chat_peer.chat.creator_id == user.id):
        raise ErrorRpc(error_code=400, error_message="CHAT_ADMIN_REQUIRED")

    target_chat_peer = await Peer.get_or_none(owner=user_peer.user, chat=chat_peer.chat)
    if target_chat_peer is None:
        raise ErrorRpc(error_code=400, error_message="USER_NOT_PARTICIPANT")

    messages = await Message.create_for_peer(
        chat_peer, None, None,
        author=user, type=MessageType.SERVICE_CHAT_USER_DEL,
        extra_info=MessageActionChatDeleteUser(user_id=user_peer.peer_user(user).id).write(),
    )
    await ChatParticipant.filter(chat=chat_peer.chat, user=user_peer.user).delete()
    await Chat.filter(id=chat_peer.chat_id).update(participants_count=F("participants_count") - 1)

    chat_peers = {peer.owner.id: peer for peer in await Peer.filter(chat=chat_peer.chat).select_related("owner")}

    updates_msg = await upd.send_message(user, messages)
    updates = await upd.create_chat(user, chat_peer.chat, list(chat_peers.values()))
    if isinstance(updates_msg, Updates):
        updates.updates.extend(updates_msg.updates)
        updates.users.extend(updates_msg.users)
        updates.chats.extend(updates_msg.chats)

    return updates


@handler.on_request(EditChatAdmin, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def edit_chat_admin(request: EditChatAdmin, user: User) -> bool:
    chat_peer = await Peer.from_chat_id_raise(user, request.chat_id)
    user_peer = await Peer.from_input_peer_raise(user, request.user_id)

    if not await Peer.filter(owner=user_peer.user, chat=chat_peer.chat).exists():
        raise ErrorRpc(error_code=400, error_message="USER_NOT_PARTICIPANT")
    if chat_peer.chat.creator_id != user.id:
        raise ErrorRpc(error_code=400, error_message="CHAT_ADMIN_REQUIRED")

    participant = await ChatParticipant.get_or_none(chat=chat_peer.chat, user=user_peer.user)
    if participant.is_admin == request.is_admin:
        return True

    if request.is_admin:
        participant.admin_rights = ChatAdminRights.from_tl(CREATOR_RIGHTS)
    else:
        participant.admin_rights = ChatAdminRights(0)

    await participant.save(update_fields=["admin_rights"])
    chat_peer.chat.version += 1
    await chat_peer.chat.save(update_fields=["version"])

    chat_peers = {peer.owner.id: peer for peer in await Peer.filter(chat=chat_peer.chat).select_related("owner")}
    await upd.create_chat(user, chat_peer.chat, list(chat_peers.values()))

    return True


@handler.on_request(ToggleNoForwards, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def toggle_no_forwards(request: ToggleNoForwards, user: User) -> Updates:
    peer = await Peer.from_input_peer_raise(user, request.peer)
    if peer.type not in (PeerType.CHAT, PeerType.CHANNEL):
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    chat_or_channel = peer.chat_or_channel

    if request.enabled == chat_or_channel.no_forwards:
        raise ErrorRpc(error_code=400, error_message="CHAT_NOT_MODIFIED")

    participant = await ChatParticipant.get_or_none(chat=chat_or_channel, user=user)
    if participant is None or not chat_or_channel.admin_has_permission(participant, ChatAdminRights.CHANGE_INFO):
        raise ErrorRpc(error_code=400, error_message="CHAT_ADMIN_REQUIRED")

    chat_or_channel.no_forwards = request.enabled
    chat_or_channel.version += 1
    await chat_or_channel.save(update_fields=["no_forwards", "version"])

    if peer.type is PeerType.CHANNEL:
        await AdminLogEntry.create(
            channel=peer.channel,
            user=user,
            action=AdminLogEntryAction.TOGGLE_NOFORWARDS,
            new=b"\x01" if request.enabled else b"\x00",
        )

    if peer.type is PeerType.CHAT:
        return await upd.update_chat(peer.chat, user)
    else:
        return await upd.update_channel(peer.channel, user)


@handler.on_request(EditChatDefaultBannedRights)
async def edit_chat_default_banned_rights(request: EditChatDefaultBannedRights, user: User) -> Updates:
    peer = await Peer.from_input_peer_raise(user, request.peer, peer_types=(PeerType.CHAT, PeerType.CHANNEL))

    participant = await ChatParticipant.get_or_none(**Chat.or_channel(peer.chat_or_channel), user=user)
    if participant is None or not (participant.is_admin or peer.chat_or_channel.creator_id == user.id):
        raise ErrorRpc(error_code=400, error_message="CHAT_ADMIN_REQUIRED")

    chat_or_channel = peer.chat_or_channel
    new_banned_rights = ChatBannedRights.from_tl(request.banned_rights)

    if chat_or_channel.banned_rights == new_banned_rights:
        raise ErrorRpc(error_code=400, error_message="CHAT_NOT_MODIFIED")

    chat_or_channel.banned_rights = new_banned_rights
    chat_or_channel.version += 1
    await chat_or_channel.save(update_fields=["banned_rights", "version"])
    # TODO: create AdminLogEntry

    if isinstance(chat_or_channel, Chat):
        return await upd.update_chat_default_banned_rights(chat_or_channel, user)
    else:
        chat_or_channel = cast(Channel, chat_or_channel)
        return await upd.update_channel(chat_or_channel, user)


@handler.on_request(MigrateChat, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def migrate_chat(request: MigrateChat, user: User) -> Updates:
    peer = await Peer.from_chat_id_raise(user, request.chat_id)
    if peer.type is not PeerType.CHAT:
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    participant = await ChatParticipant.get_or_none(chat=peer.chat, user=user)
    if participant is None or not (participant.is_admin or peer.chat.creator_id == user.id):
        raise ErrorRpc(error_code=400, error_message="CHAT_ADMIN_REQUIRED")

    chat = peer.chat
    await chat.fetch_related("creator", "photo")

    participants = await ChatParticipant.filter(chat=chat).select_related("user")

    async with in_transaction():
        channel = await Channel.create(
            creator=chat.creator,
            name=chat.name,
            description=chat.description,
            channel=False,
            supergroup=True,
            migrated_from=chat,
            no_forwards=chat.no_forwards,
            banned_rights=chat.banned_rights,
            ttl_period_days=chat.ttl_period_days,
            photo=chat.photo,
        )

        peers_to_create = [Peer(owner=None, type=PeerType.CHANNEL, channel=channel)]
        participants_to_create = []

        for participant in participants:
            peers_to_create.append(Peer(owner=participant.user, type=PeerType.CHANNEL, channel=channel))
            if chat.creator_id == participant.user_id:
                admin_rights = ChatAdminRights.from_tl(CREATOR_RIGHTS)
            else:
                admin_rights = participant.admin_rights
            participants_to_create.append(ChatParticipant(
                user=participant.user,
                channel=channel,
                inviter_id=participant.inviter_id,
                invited_at=participant.invited_at,
                banned_until=participant.banned_until,
                banned_rights=participant.banned_rights,
                admin_rights=admin_rights,
                admin_rank=participant.admin_rank,
                promoted_by_id=participant.promoted_by_id,
            ))

        await Peer.bulk_create(peers_to_create)
        new_peers = await Peer.filter(channel=channel, owner__id__not_isnull=True)

        dialogs_to_create = []
        for new_peer in new_peers:
            dialogs_to_create.append(Dialog(peer=new_peer, visible=True))

        await Chat.filter(id=chat.id).update(migrated=True, version=F("version") + 1)
        await chat.refresh_from_db(["migrated", "version"])

        await Message.filter(id__in=Subquery(
            Message.filter(peer__chat=chat, type=MessageType.SCHEDULED).values_list("id", flat=True)
        )).delete()
        await ChatInvite.filter(chat=chat).update(revoked=True)
        await ChatInviteRequest.filter(id__in=Subquery(
            ChatInviteRequest.filter(invite__chat=chat).values_list("id", flat=True)
        )).delete()

        await ChatParticipant.bulk_create(participants_to_create)
        await Dialog.bulk_create(dialogs_to_create)
        await Dialog.filter(id__in=Subquery(
            Dialog.filter(peer__chat=chat).values_list("id", flat=True)
        )).update(visible=False)

    await SessionManager.subscribe_to_channel(channel.id, [new_peer.owner_id for new_peer in new_peers])

    updates = await upd.migrate_chat(chat, channel, user)

    msg_updates = await send_message_internal(
        user, peer, None, None, False, unhide_dialog=False,
        author=user, type=MessageType.SERVICE_CHAT_MIGRATE_TO,
        extra_info=MessageActionChatMigrateTo(channel_id=channel.make_id()).write(),
    )
    updates.updates.extend(msg_updates.updates)

    peer_channel = await Peer.get(owner=user, channel=channel).select_related("owner", "channel")
    msg_updates = await send_message_internal(
        user, peer_channel, None, None, False, unhide_dialog=False,
        author=user, type=MessageType.SERVICE_CHAT_MIGRATE_FROM,
        extra_info=MessageActionChannelMigrateFrom(title=chat.name, chat_id=chat.make_id()).write(),
    )
    updates.updates.extend(msg_updates.updates)

    return updates


@handler.on_request(GetOnlines)
async def get_onlines(request: GetOnlines, user: User) -> ChatOnlines:
    peer = await Peer.from_input_peer_raise(user, request.peer, peer_types=(PeerType.CHAT, PeerType.CHANNEL))

    onlines = await Presence.filter(
        status=UserStatus.ONLINE, last_seen__gt=datetime.now(UTC) - timedelta(minutes=1), user__id__in=Subquery(
            ChatParticipant.filter(**Chat.or_channel(peer.chat_or_channel)).values_list("user__id", flat=True)
        )
    ).count()

    return ChatOnlines(onlines=onlines)

