from time import time

from fastrand import xorshift128plus_bytes

import piltover.app.utils.updates_manager as upd
from piltover.db.enums import PeerType
from piltover.db.models import User, Peer, Presence
from piltover.exceptions import ErrorRpc
from piltover.session_manager import SessionManager
from piltover.tl import Updates, UpdateUserTyping, DefaultHistoryTTL
from piltover.tl.functions.messages import SetTyping, GetDhConfig, GetDefaultHistoryTTL, SetDefaultHistoryTTL, \
    SetHistoryTTL
from piltover.tl.types.messages import DhConfig, DhConfigNotModified
from piltover.utils import gen_safe_prime
from piltover.utils.gen_primes import CURRENT_DH_VERSION
from piltover.worker import MessageHandler

handler = MessageHandler("messages.other")


@handler.on_request(SetTyping)
async def set_typing(request: SetTyping, user: User):
    peer = await Peer.from_input_peer_raise(user, request.peer)
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
    await upd.update_status(user, presence, peers)

    return True


@handler.on_request(GetDhConfig)
async def get_dh_config(request: GetDhConfig):
    random_bytes = xorshift128plus_bytes(min(1024, request.random_length)) if request.random_length else b""

    if request.version == CURRENT_DH_VERSION:
        return DhConfigNotModified(random=random_bytes)

    prime, g = gen_safe_prime()

    return DhConfig(
        p=prime.to_bytes(256, "big"),
        g=g,
        version=CURRENT_DH_VERSION,
        random=random_bytes,
    )


@handler.on_request(GetDefaultHistoryTTL)
async def get_default_history_ttl(user: User) -> DefaultHistoryTTL:
    return DefaultHistoryTTL(period=user.history_ttl_days * 86400)


@handler.on_request(SetDefaultHistoryTTL)
async def set_default_history_ttl(request: SetDefaultHistoryTTL, user: User) -> bool:
    if request.period % 86400 != 0:
        raise ErrorRpc(error_code=400, error_message="TTL_PERIOD_INVALID")

    user.history_ttl_days = request.period // 86400
    await user.save(update_fields=["history_ttl_days"])

    return True
