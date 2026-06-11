from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from piltover import tl
    from piltover.tl.serialization_context import SerializationContext


def downgrade_peers_for_135(obj: tl.types.channels.SendAsPeers, _: SerializationContext) -> list[tl.base.Peer]:
    return [
        send_as_peer.peer
        for send_as_peer in obj.peers
        if not send_as_peer.premium_required
    ]
