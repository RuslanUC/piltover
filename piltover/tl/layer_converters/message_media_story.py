from __future__ import annotations
from typing import TYPE_CHECKING
from piltover import tl

if TYPE_CHECKING:
    from piltover.tl.serialization_context import SerializationContext


def get_user_id_fallback_for_160(obj: tl.types.MessageMediaStory, _: SerializationContext) -> int:
    if isinstance(obj.peer, tl.types.PeerUser):
        return obj.peer.user_id
    return 0
