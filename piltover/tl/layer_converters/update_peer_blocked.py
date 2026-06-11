from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from piltover import tl
    from piltover.tl.serialization_context import SerializationContext


def downgrade_blocked_for_133(obj: tl.types.UpdatePeerBlocked, _: SerializationContext) -> bool:
    return obj.blocked
