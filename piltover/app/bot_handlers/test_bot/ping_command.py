from piltover.db.models import Peer, MessageRef


async def test_bot_ping_command(peer: Peer, _: MessageRef) -> MessageRef | None:
    messages = await MessageRef.create_for_peer(peer, peer.user, opposite=False, message="Pong")
    return messages[peer]
