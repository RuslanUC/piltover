from piltover.app.messages.sending import send_message_internal
from piltover.app.utils.updates_manager import UpdatesManager
from piltover.app.utils.utils import resize_photo, generate_stripped
from piltover.db.enums import PeerType, MessageType
from piltover.db.models import User, Peer, Chat, File, UploadingFile, ChatParticipant, Message
from piltover.exceptions import ErrorRpc
from piltover.tl import MissingInvitee, InputUserFromMessage, InputUser, Updates, ChatFull, PeerNotifySettings, \
    ChatParticipantCreator, ChatParticipants, InputChatPhotoEmpty, InputChatPhoto, InputChatUploadedPhoto, PhotoEmpty, \
    InputPeerUser
from piltover.tl.functions.messages import CreateChat, GetChats, CreateChat_150, GetFullChat, EditChatTitle, \
    EditChatAbout, EditChatPhoto, AddChatUser
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
    updates_msg = await send_message_internal(
        user, chat_peers[user.id], None, None, False,
        author=user, type=MessageType.SERVICE_CHAT_CREATE, message=request.title,
    )

    if isinstance(updates_msg, Updates):
        updates.updates.extend(updates_msg.updates)

    return InvitedUsers(
        updates=updates,
        missing_invitees=missing,
    )


@handler.on_request(GetChats)
async def get_chats(request: GetChats, user: User) -> Chats:
    peers = await Peer.filter(owner=user, chat__id__in=[request.id]).select_related("chat")
    return Chats(
        chats=[
            await peer.chat.to_tl(user)
            for peer in peers
        ]
    )


@handler.on_request(GetFullChat)
async def get_full_chat(request: GetFullChat, user: User) -> MessagesChatFull:
    if (peer := await Peer.from_chat_id(user, request.chat_id)) is None:
        raise ErrorRpc(error_code=400, error_message="CHAT_ID_INVALID")

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
                    ChatParticipantCreator(user_id=user.id),
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
    if (peer := await Peer.from_chat_id(user, request.chat_id)) is None:
        raise ErrorRpc(error_code=400, error_message="CHAT_ID_INVALID")

    # TODO: check if admin
    chat = peer.chat

    new_title = request.title.strip()
    if new_title == chat.name:
        raise ErrorRpc(error_code=400, error_message="CHAT_NOT_MODIFIED")
    if not new_title:
        raise ErrorRpc(error_code=400, error_message="CHAT_TITLE_EMPTY")

    chat.name = new_title
    await chat.save(update_fields=["name"])

    return await send_message_internal(
        user, peer, None, None, False,
        author=user, type=MessageType.SERVICE_CHAT_EDIT_TITLE, message=request.title,
    )


@handler.on_request(EditChatAbout)
async def edit_chat_about(request: EditChatAbout, user: User) -> bool:
    if (peer := await Peer.from_input_peer(user, request.peer)) is None:
        raise ErrorRpc(error_code=400, error_message="CHAT_ID_INVALID")
    if peer.type is not PeerType.CHAT:
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    # TODO: check if admin
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
    if (peer := await Peer.from_chat_id(user, request.chat_id)) is None:
        raise ErrorRpc(error_code=400, error_message="CHAT_ID_INVALID")

    # TODO: check if admin
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

    await chat.save()

    return await send_message_internal(
        user, peer, None, None, False,
        author=user, type=MessageType.SERVICE_CHAT_EDIT_PHOTO, message=str(chat.photo.id if chat.photo else 0),
    )


@handler.on_request(AddChatUser)
async def add_chat_user(request: AddChatUser, user: User):
    if (chat_peer := await Peer.from_chat_id(user, request.chat_id)) is None:
        raise ErrorRpc(error_code=400, error_message="CHAT_ID_INVALID")
    if (user_peer := await Peer.from_input_peer(user, request.user_id)) is None:
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    # TODO: check if admin / has chat permissions to add users / has permission to add this specific user

    chat_peers = {peer.owner.id: peer for peer in await Peer.filter(chat=chat_peer.chat).select_related("owner")}
    if chat_peer.owner.id not in chat_peers:
        chat_peers[chat_peer.owner.id] = chat_peer
    invited_user = user_peer.peer_user(user)
    if user_peer.peer_user(user).id not in chat_peers:
        chat_peers[invited_user.id] = await Peer.create(owner=invited_user, chat=chat_peer.chat, type=PeerType.CHAT)
        await ChatParticipant.create(user=invited_user, chat=chat_peer.chat, inviter_id=user.id)

    # TODO: do nothing if user is already in chat ?

    updates = await UpdatesManager.create_chat(user, chat_peer.chat, list(chat_peers.values()))

    if request.fwd_limit > 0:
        limit = min(request.fwd_limit, 100)
        messages_to_forward = await Message.filter(
            peer=chat_peer, type=MessageType.REGULAR
        ).order_by("-id").limit(limit).select_related("author", "media", "reply_to", "fwd_header")
        messages = []
        for message in messages_to_forward:
            messages.append(await Message.create(
                peer=chat_peers[invited_user.id],
                author=message.author,
                media=message.media,
                #reply_to=message.reply_to,  # TODO: replies
                fwd_header=message.fwd_header,

                internal_id=message.internal_id,
                message=message.message,
                pinned=message.pinned,
                date=message.date,
                edit_date=message.edit_date,
            ))

        await UpdatesManager.send_messages({chat_peers[invited_user.id]: messages})

    updates_msg = await send_message_internal(
        user, chat_peers[user.id], None, None, False,
        author=user, type=MessageType.SERVICE_CHAT_USER_ADD, message=str(invited_user.id),
    )

    if isinstance(updates_msg, Updates):
        updates.updates.extend(updates_msg.updates)

    return InvitedUsers(
        updates=updates,
        missing_invitees=[],
    )


# TODO: DeleteChatUser
