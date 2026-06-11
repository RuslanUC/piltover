from __future__ import annotations
from typing import TYPE_CHECKING
from piltover import tl

if TYPE_CHECKING:
    from piltover.tl.serialization_context import SerializationContext


def get_user_id_fallback_for_160(obj: tl.types.InputReplyToStory, _: SerializationContext) -> tl.base.InputUser:
    if isinstance(obj.peer, tl.types.InputPeerUser):
        return tl.types.InputUser(user_id=obj.peer.user_id, access_hash=obj.peer.access_hash)
    return tl.types.InputUser(user_id=0, access_hash=0)
