from time import time

from fastrand import xorshift128plus_bytes

import piltover.app.utils.updates_manager as upd
from piltover.db.enums import PeerType
from piltover.db.models import User, Peer, Presence, ChatParticipant
from piltover.enums import ReqHandlerFlags
from piltover.exceptions import ErrorRpc
from piltover.session_manager import SessionManager
from piltover.tl import UpdateUserTyping, DefaultHistoryTTL, UpdateChatUserTyping, UpdateChannelUserTyping
from piltover.tl.functions.messages import SetTyping, GetDhConfig, GetDefaultHistoryTTL, SetDefaultHistoryTTL
from piltover.tl.types.internal import LazyUser
from piltover.tl.types.messages import DhConfig, DhConfigNotModified
from piltover.utils import gen_safe_prime
from piltover.utils.gen_primes import CURRENT_DH_VERSION
from piltover.worker import MessageHandler

handler = MessageHandler("messages.other")


@handler.on_request(SetTyping)
async def set_typing(request: SetTyping, user: User):
    peer = await Peer.from_input_peer_raise(user, request.peer)

    if peer.type == PeerType.SELF or (peer.type is PeerType.CHANNEL and not peer.channel.supergroup):
        return True
    elif peer.type is PeerType.USER:
        peers = await peer.get_opposite()
        if not peers:
            return True

        await SessionManager.send(
            upd.UpdatesWithDefaults(
                updates=[UpdateUserTyping(user_id=user.id, action=request.action)],
                users=[LazyUser(user_id=user.id)],
            ),
            user_id=[other.owner_id for other in peers],
        )
    elif peer.type is PeerType.CHAT:
        peers = await peer.get_opposite()
        if not peers:
            return True

        await SessionManager.send(
            upd.UpdatesWithDefaults(
                updates=[UpdateChatUserTyping(
                    chat_id=peer.chat_id,
                    from_id=user.to_tl_peer(),
                    action=request.action,
                )],
                users=[LazyUser(user_id=user.id)],
                chats=[await peer.chat.to_tl()],
            ),
            user_id=[other.owner_id for other in peers],
        )
    elif peer.type is PeerType.CHANNEL:
        # TODO: support top_msg_id

        channel = peer.channel

        participant = await ChatParticipant.get_or_none(channel=channel, user=user, left=False)
        if participant is None and channel.join_to_send:
            raise ErrorRpc(error_code=400, error_message="USER_BANNED_IN_CHANNEL")
        if participant is not None and not channel.can_send_messages(participant):
            raise ErrorRpc(error_code=400, error_message="USER_BANNED_IN_CHANNEL")

        await SessionManager.send(
            upd.UpdatesWithDefaults(
                updates=[UpdateChannelUserTyping(
                    channel_id=peer.channel_id,
                    from_id=user.to_tl_peer(),
                    action=request.action,
                )],
                users=[LazyUser(user_id=user.id)],
                chats=[await peer.channel.to_tl()],
            ),
            channel_id=peer.channel_id,
        )

    if not user.bot:
        await Presence.update_to_now(user)
        # TODO: send status update
        #await upd.update_status(user, presence, peers)

    return True


@handler.on_request(GetDhConfig, ReqHandlerFlags.BOT_NOT_ALLOWED)
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


@handler.on_request(GetDefaultHistoryTTL, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def get_default_history_ttl(user: User) -> DefaultHistoryTTL:
    return DefaultHistoryTTL(period=user.history_ttl_days * 86400)


@handler.on_request(SetDefaultHistoryTTL, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def set_default_history_ttl(request: SetDefaultHistoryTTL, user: User) -> bool:
    if request.period % 86400 != 0:
        raise ErrorRpc(error_code=400, error_message="TTL_PERIOD_INVALID")

    user.history_ttl_days = request.period // 86400
    await user.save(update_fields=["history_ttl_days"])

    return True
