from time import time

from piltover.app.utils.updates_manager import UpdatesManager
from piltover.db.enums import PeerType
from piltover.db.models import User, Peer, Presence
from piltover.exceptions import ErrorRpc
from piltover.high_level import MessageHandler
from piltover.session_manager import SessionManager
from piltover.tl import Updates, UpdateUserTyping
from piltover.tl.functions.messages import SetTyping

handler = MessageHandler("messages.other")


@handler.on_request(SetTyping)
async def set_typing(request: SetTyping, user: User):
    if (peer := await Peer.from_input_peer(user, request.peer)) is None:
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    if peer.type == PeerType.SELF:
        return True

    chat = peer.chat if peer.type is PeerType.CHAT else None
    peers = await peer.get_opposite()
    for other in peers:
        chats = [] if chat is None else [await chat.to_tl(other.owner)]
        updates = Updates(
            updates=[UpdateUserTyping(user_id=user.id, action=request.action)],
            users=[await user.to_tl(other.owner)],
            chats=chats,
            date=int(time()),
            seq=0,
        )
        await SessionManager.send(updates, other.id)

    presence = await Presence.update_to_now(user)
    await UpdatesManager.update_status(user, presence, peers)

    return True
