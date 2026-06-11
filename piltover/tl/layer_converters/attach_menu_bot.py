from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from piltover import tl
    from piltover.tl.serialization_context import SerializationContext


def downgrade_peer_types_for_143(obj: tl.types.AttachMenuBot, _: SerializationContext) -> list[tl.base.AttachMenuPeerType]:
    if obj.peer_types is not None:
        return obj.peer_types
    return []
