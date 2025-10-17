from tortoise.expressions import Subquery

import piltover.app.utils.updates_manager as upd
from piltover.app.handlers.messages.sending import send_message_internal
from piltover.app.utils.utils import resize_photo, generate_stripped
from piltover.app_config import AppConfig
from piltover.context import request_ctx
from piltover.db.enums import PeerType, MessageType, PrivacyRuleKeyType, ChatBannedRights, ChatAdminRights, FileType
from piltover.db.models import User, Peer, Chat, File, UploadingFile, ChatParticipant, Message, PrivacyRule, \
    ChatInviteRequest
from piltover.exceptions import ErrorRpc
from piltover.tl import MissingInvitee, InputUserFromMessage, InputUser, Updates, ChatFull, PeerNotifySettings, \
    ChatParticipants, InputChatPhotoEmpty, InputChatPhoto, InputChatUploadedPhoto, PhotoEmpty, InputPeerUser, \
    Long, MessageActionChatCreate, MessageActionChatEditTitle, MessageActionChatAddUser, \
    MessageActionChatDeleteUser
from piltover.tl.functions.messages import CreateChat, GetChats, CreateChat_150, GetFullChat, EditChatTitle, \
    EditChatAbout, EditChatPhoto, AddChatUser, DeleteChatUser, AddChatUser_133, EditChatAdmin, ToggleNoForwards, \
    EditChatDefaultBannedRights, CreateChat_133
from piltover.tl.types.messages import InvitedUsers, Chats, ChatFull as MessagesChatFull
from piltover.worker import MessageHandler

handler = MessageHandler("messages.chats")


@handler.on_request(CreateChat_133)
@handler.on_request(CreateChat_150)
@handler.on_request(CreateChat)
async def create_chat(request: CreateChat, user: User) -> InvitedUsers:
    chat = await Chat.create(name=request.title, creator=user)
    chat_peers = {user.id: await Peer.create(owner=user, chat=chat, type=PeerType.CHAT)}

    participants_to_create = [ChatParticipant(user=user, chat=chat)]

    missing = []
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

    await ChatParticipant.bulk_create(participants_to_create)

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
    peers = await Peer.filter(owner=user, chat__id__in=request.id).select_related("chat")
    return Chats(
        chats=[
            await peer.chat.to_tl(user)
            for peer in peers
        ],
    )


@handler.on_request(GetFullChat)
async def get_full_chat(request: GetFullChat, user: User) -> MessagesChatFull:
    peer = await Peer.from_chat_id_raise(user, request.chat_id)

    chat = peer.chat
    photo = PhotoEmpty(id=0)
    if chat.photo_id:
        await chat.fetch_related("photo")
        photo = await chat.photo.to_tl_photo(user)

    return MessagesChatFull(
        full_chat=ChatFull(
            can_set_username=True,
            translations_disabled=True,
            id=chat.id,
            about=chat.description,
            participants=ChatParticipants(
                chat_id=chat.id,
                participants=[
                    await participant.to_tl()
                    for participant in await ChatParticipant.filter(chat=chat).select_related("chat")
                ],
                version=chat.version,
            ),
            notify_settings=PeerNotifySettings(),
            chat_photo=photo,
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
    peer = await Peer.from_input_peer_raise(user, request.peer)
    if peer.type is not PeerType.CHAT:
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    participant = await ChatParticipant.get_or_none(chat=peer.chat, user=user)
    if participant is None or not (participant.is_admin or peer.chat.creator_id == user.id):
        raise ErrorRpc(error_code=400, error_message="CHAT_ADMIN_REQUIRED")

    chat = peer.chat
    await chat.update(description=request.about)
    await upd.update_chat(chat)

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
        file = await uploaded_file.finalize_upload(storage, "image/png", file_type=FileType.PHOTO)
        # TODO: replace this functions with something like generate_thumbnails
        file.photo_sizes = await resize_photo(storage, file.physical_id)
        file.photo_stripped = await generate_stripped(storage, file.physical_id)
        await file.save(update_fields=["photo_sizes", "photo_stripped"])

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
        extra_info=Long.write(chat.photo.id if chat.photo else 0),
    )


@handler.on_request(AddChatUser_133)
@handler.on_request(AddChatUser)
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

    chat_peers = {peer.owner.id: peer for peer in await Peer.filter(chat=chat_peer.chat).select_related("owner")}
    if chat_peer.owner.id not in chat_peers:
        chat_peers[chat_peer.owner.id] = chat_peer
    invited_user = user_peer.peer_user(user)
    if user_peer.peer_user(user).id not in chat_peers:
        chat_peers[invited_user.id] = await Peer.create(owner=invited_user, chat=chat_peer.chat, type=PeerType.CHAT)
        await ChatParticipant.create(user=invited_user, chat=chat_peer.chat, inviter_id=user.id)
        await ChatInviteRequest.filter(id__in=Subquery(
            ChatInviteRequest.filter(user=invited_user, invite__chat=chat_peer.chat).values_list("id", flat=True)
        )).delete()

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

    chat_peers = {peer.owner.id: peer for peer in await Peer.filter(chat=chat_peer.chat).select_related("owner")}

    updates_msg = await upd.send_message(user, messages)
    updates = await upd.create_chat(user, chat_peer.chat, list(chat_peers.values()))
    if isinstance(updates_msg, Updates):
        updates.updates.extend(updates_msg.updates)
        updates.users.extend(updates_msg.users)
        updates.chats.extend(updates_msg.chats)

    return updates


@handler.on_request(EditChatAdmin)
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
        participant.admin_rights = ChatAdminRights.all()
    else:
        participant.admin_rights = ChatAdminRights(0)

    await participant.save(update_fields=["admin_rights"])
    chat_peer.chat.version += 1
    await chat_peer.chat.save(update_fields=["version"])

    chat_peers = {peer.owner.id: peer for peer in await Peer.filter(chat=chat_peer.chat).select_related("owner")}
    await upd.create_chat(user, chat_peer.chat, list(chat_peers.values()))

    return True


@handler.on_request(ToggleNoForwards)
async def toggle_no_forwards(request: ToggleNoForwards, user: User) -> Updates:
    peer = await Peer.from_input_peer_raise(user, request.peer)
    if peer.type is not PeerType.CHAT:
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    participant = await ChatParticipant.get_or_none(chat=peer.chat, user=user)
    if participant is None or not (participant.is_admin or peer.chat.creator_id == user.id):
        raise ErrorRpc(error_code=400, error_message="CHAT_ADMIN_REQUIRED")

    chat = peer.chat
    if request.enabled == chat.no_forwards:
        raise ErrorRpc(error_code=400, error_message="CHAT_NOT_MODIFIED")

    chat.no_forwards = request.enabled
    chat.version += 1
    await chat.save(update_fields=["no_forwards", "version"])

    return await upd.update_chat(chat, user)


@handler.on_request(EditChatDefaultBannedRights)
async def edit_chat_default_banned_rights(request: EditChatDefaultBannedRights, user: User) -> Updates:
    peer = await Peer.from_input_peer_raise(user, request.peer)
    if peer.type is not PeerType.CHAT:
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    participant = await ChatParticipant.get_or_none(chat=peer.chat, user=user)
    if participant is None or not (participant.is_admin or peer.chat.creator_id == user.id):
        raise ErrorRpc(error_code=400, error_message="CHAT_ADMIN_REQUIRED")

    chat = peer.chat
    new_banned_rights = ChatBannedRights.from_tl(request.banned_rights)

    if chat.banned_rights == new_banned_rights:
        raise ErrorRpc(error_code=400, error_message="CHAT_NOT_MODIFIED")

    chat.banned_rights = new_banned_rights
    chat.version += 1
    await chat.save(update_fields=["banned_rights", "version"])

    return await upd.update_chat_default_banned_rights(chat, user)
