from piltover.app.messages.sending import send_message_internal
from piltover.app.utils.updates_manager import UpdatesManager
from piltover.db.enums import PeerType, MessageType
from piltover.db.models import User, Peer, Chat
from piltover.exceptions import ErrorRpc
from piltover.high_level import MessageHandler
from piltover.tl import MissingInvitee, InputUserFromMessage, InputUser, Updates, ChatFull, PeerNotifySettings, \
    ChatParticipantCreator, ChatParticipants
from piltover.tl.functions.messages import CreateChat, GetChats, CreateChat_150, GetFullChat
from piltover.tl.types.messages import InvitedUsers, Chats, ChatFull as MessagesChatFull

handler = MessageHandler("messages.chats")


@handler.on_request(CreateChat_150)
@handler.on_request(CreateChat)
async def create_chat(request: CreateChat, user: User) -> InvitedUsers:
    chat = await Chat.create(name=request.title, creator=user)
    peer_chat = await Peer.create(owner=user, chat=chat, type=PeerType.CHAT)

    updates = await UpdatesManager.create_chat(user, chat, [peer_chat])
    updates_msg = await send_message_internal(
        user, peer_chat, None, None, False, author=user, type=MessageType.SERVICE_CHAT_CREATE
    )

    if isinstance(updates_msg, Updates):
        updates.updates.extend(updates_msg.updates)

    return InvitedUsers(
        updates=updates,
        missing_invitees=[
            MissingInvitee(user_id=input_user.user_id)
            for input_user in request.users
            if isinstance(input_user, (InputUser, InputUserFromMessage)) and input_user.user_id != user.id
        ]
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

    return MessagesChatFull(
        full_chat=ChatFull(
            can_set_username=True,
            translations_disabled=True,
            id=chat.id,
            about="",
            participants=ChatParticipants(
                chat_id=chat.id,
                participants=[
                    ChatParticipantCreator(user_id=user.id)
                ],
                version=1,
            ),
            notify_settings=PeerNotifySettings(),
        ),
        chats=[await chat.to_tl(user)],
        users=[await user.to_tl(user)],
    )
