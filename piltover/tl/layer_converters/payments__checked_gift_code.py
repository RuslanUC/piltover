from __future__ import annotations
from typing import TYPE_CHECKING
from piltover import tl

if TYPE_CHECKING:
    from piltover.tl.serialization_context import SerializationContext


def downgrade_from_id_for_166(obj: tl.types.payments.CheckedGiftCode, _: SerializationContext) -> tl.base.Peer:
    if obj.from_id is not None:
        return obj.from_id
    return tl.types.PeerUser(user_id=0)
