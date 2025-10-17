from piltover.db.models import Peer, Message


async def test_bot_ping_command(peer: Peer, message: Message) -> Message | None:
    messages = await Message.create_for_peer(peer, None, None, peer.user, False, message="Pong")
    return messages[peer]
