from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from piltover import tl
    from piltover.tl.serialization_context import SerializationContext


def get_peer_fallback_for_152(obj: tl.types.MessageActionRequestedPeer, _: SerializationContext) -> tl.base.Peer:
    return obj.peers[0]
