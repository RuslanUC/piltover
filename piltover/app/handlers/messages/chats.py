from piltover.app.handlers.messages.sending import send_message_internal, create_message_internal
from piltover.app.utils.updates_manager import UpdatesManager
from piltover.app.utils.utils import resize_photo, generate_stripped
from piltover.db.enums import PeerType, MessageType, PrivacyRuleKeyType
from piltover.db.models import User, Peer, Chat, File, UploadingFile, ChatParticipant, Message, PrivacyRule
from piltover.exceptions import ErrorRpc
from piltover.tl import MissingInvitee, InputUserFromMessage, InputUser, Updates, ChatFull, PeerNotifySettings, \
    ChatParticipants, InputChatPhotoEmpty, InputChatPhoto, InputChatUploadedPhoto, PhotoEmpty, \
    InputPeerUser, SerializationUtils, Vector, Long
from piltover.tl.functions.messages import CreateChat, GetChats, CreateChat_150, GetFullChat, EditChatTitle, \
    EditChatAbout, EditChatPhoto, AddChatUser, DeleteChatUser, AddChatUser_136, EditChatAdmin
from piltover.tl.types.messages import InvitedUsers, Chats, ChatFull as MessagesChatFull
from piltover.worker import MessageHandler

handler = MessageHandler("messages.chats")


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

    updates = await UpdatesManager.create_chat(user, chat, list(chat_peers.values()))
    extra_info = (SerializationUtils.write(request.title) + Vector(chat_peers.keys(), value_type=Long).write())
    updates_msg = await send_message_internal(
        user, chat_peers[user.id], None, None, False,
        author=user, type=MessageType.SERVICE_CHAT_CREATE, extra_info=extra_info,
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

    chat = peer.chat

    new_title = request.title.strip()
    if new_title == chat.name:
        raise ErrorRpc(error_code=400, error_message="CHAT_NOT_MODIFIED")
    if not new_title:
        raise ErrorRpc(error_code=400, error_message="CHAT_TITLE_EMPTY")

    chat.name = new_title
    chat.version += 1
    await chat.save(update_fields=["name", "version"])

    return await send_message_internal(
        user, peer, None, None, False,
        author=user, type=MessageType.SERVICE_CHAT_EDIT_TITLE, extra_info=SerializationUtils.write(request.title),
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

    new_desc = request.about.strip()
    if new_desc == chat.name:
        raise ErrorRpc(error_code=400, error_message="CHAT_ABOUT_NOT_MODIFIED")
    if len(new_desc) > 255:
        raise ErrorRpc(error_code=400, error_message="CHAT_ABOUT_TOO_LONG")

    chat.description = new_desc
    chat.version += 1
    await chat.save(update_fields=["description", "version"])

    await UpdatesManager.update_chat(chat)

    return True


@handler.on_request(EditChatPhoto)
async def edit_chat_photo(request: EditChatPhoto, user: User):
    peer = await Peer.from_chat_id_raise(user, request.chat_id)

    participant = await ChatParticipant.get_or_none(chat=peer.chat, user=user)
    if participant is None or not (participant.is_admin or peer.chat.creator_id == user.id):
        raise ErrorRpc(error_code=400, error_message="CHAT_ADMIN_REQUIRED")

    chat = peer.chat
    before = chat.photo

    if isinstance(request.photo, InputChatPhotoEmpty):
        chat.photo = None
    elif isinstance(request.photo, InputChatPhoto):
        if not await Peer.filter(owner=user, chat__photo__id=request.photo.id).exists():
            raise ErrorRpc(error_code=400, error_message="PHOTO_INVALID")
        chat.photo = await File.get_or_none(id=request.photo.id)
    elif isinstance(request.photo, InputChatUploadedPhoto):
        if request.photo.file is None:
            raise ErrorRpc(error_code=400, error_message="PHOTO_FILE_MISSING")
        uploaded_file = await UploadingFile.get_or_none(user=user, file_id=request.photo.file.id)
        if uploaded_file is None:
            raise ErrorRpc(error_code=400, error_message="INPUT_FILE_INVALID")

        file = await uploaded_file.finalize_upload("image/png", [])
        file.photo_sizes = await resize_photo(str(file.physical_id))
        file.photo_stripped = await generate_stripped(str(file.physical_id))
        await file.save(update_fields=["photo_sizes", "photo_stripped"])

        chat.photo = file

    if chat.photo == before:
        raise ErrorRpc(error_code=400, error_message="CHAT_NOT_MODIFIED")

    chat.version += 1
    await chat.save()

    return await send_message_internal(
        user, peer, None, None, False,
        author=user, type=MessageType.SERVICE_CHAT_EDIT_PHOTO,
        extra_info=Long.write(chat.photo.id if chat.photo else 0),
    )


@handler.on_request(AddChatUser_136)
@handler.on_request(AddChatUser)
async def add_chat_user(request: AddChatUser, user: User):
    chat_peer = await Peer.from_chat_id_raise(user, request.chat_id)
    user_peer = await Peer.from_input_peer_raise(user, request.user_id)

    if await Peer.filter(owner=user_peer.user, chat=chat_peer.chat).exists():
        raise ErrorRpc(error_code=400, error_message="USER_ALREADY_PARTICIPANT")

    if not await PrivacyRule.has_access_to(user, user_peer.user, PrivacyRuleKeyType.CHAT_INVITE):
        raise ErrorRpc(error_code=403, error_message="USER_PRIVACY_RESTRICTED")

    chat_peers = {peer.owner.id: peer for peer in await Peer.filter(chat=chat_peer.chat).select_related("owner")}
    if chat_peer.owner.id not in chat_peers:
        chat_peers[chat_peer.owner.id] = chat_peer
    invited_user = user_peer.peer_user(user)
    if user_peer.peer_user(user).id not in chat_peers:
        chat_peers[invited_user.id] = await Peer.create(owner=invited_user, chat=chat_peer.chat, type=PeerType.CHAT)
        await ChatParticipant.create(user=invited_user, chat=chat_peer.chat, inviter_id=user.id)

    updates = await UpdatesManager.create_chat(user, chat_peer.chat, list(chat_peers.values()))

    if request.fwd_limit > 0:
        limit = min(request.fwd_limit, 100)
        messages_to_forward = await Message.filter(
            peer=chat_peer, type=MessageType.REGULAR
        ).order_by("-id").limit(limit).select_related("author", "media", "reply_to", "fwd_header")
        messages = []
        for message in reversed(messages_to_forward):
            messages.append(await message.clone_for_peer(chat_peers[invited_user.id], internal_id=message.internal_id))

        await UpdatesManager.send_messages({chat_peers[invited_user.id]: messages})

    updates_msg = await send_message_internal(
        user, chat_peers[user.id], None, None, False,
        author=user, type=MessageType.SERVICE_CHAT_USER_ADD,
        extra_info=Vector([invited_user.id], value_type=Long).write(),
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

    messages = await create_message_internal(
        user, chat_peer, None, None, False,
        author=user, type=MessageType.SERVICE_CHAT_USER_DEL, extra_info=Long.write(user_peer.peer_user(user).id),
    )
    await target_chat_peer.delete()
    await ChatParticipant.filter(chat=chat_peer.chat, user=user_peer.user).delete()

    chat_peers = {peer.owner.id: peer for peer in await Peer.filter(chat=chat_peer.chat).select_related("owner")}

    updates_msg = await UpdatesManager.send_message(user, messages)
    updates = await UpdatesManager.create_chat(user, chat_peer.chat, list(chat_peers.values()))
    if isinstance(updates_msg, Updates):
        updates.updates.extend(updates_msg.updates)
        updates.users.extend(updates_msg.users)
        updates.chats.extend(updates_msg.chats)

    return updates


@handler.on_request(EditChatAdmin)
async def edit_chat_admin(request: EditChatAdmin, user: User):
    chat_peer = await Peer.from_chat_id_raise(user, request.chat_id)
    user_peer = await Peer.from_input_peer_raise(user, request.user_id)

    if not await Peer.filter(owner=user_peer.user, chat=chat_peer.chat).exists():
        raise ErrorRpc(error_code=400, error_message="USER_NOT_PARTICIPANT")
    if chat_peer.chat.creator_id != user.id:
        raise ErrorRpc(error_code=400, error_message="CHAT_ADMIN_REQUIRED")

    participant = await ChatParticipant.get_or_none(chat=chat_peer.chat, user=user_peer.user)
    if participant.is_admin == request.is_admin:
        return True

    participant.is_admin = request.is_admin
    await participant.save(update_fields=["is_admin"])
    chat_peer.chat.version += 1
    await chat_peer.chat.save(update_fields=["version"])

    chat_peers = {peer.owner.id: peer for peer in await Peer.filter(chat=chat_peer.chat).select_related("owner")}
    await UpdatesManager.create_chat(user, chat_peer.chat, list(chat_peers.values()))

    return True
