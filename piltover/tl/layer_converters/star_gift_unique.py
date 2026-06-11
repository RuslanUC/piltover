from __future__ import annotations
from typing import TYPE_CHECKING
from piltover import tl

if TYPE_CHECKING:
    from piltover.tl.serialization_context import SerializationContext


def downgrade_owner_id_for_196(obj: tl.types.StarGiftUnique, _: SerializationContext) -> int:
    if not isinstance(obj.owner_id, tl.types.PeerUser):
        return 0
    return obj.owner_id.user_id


def downgrade_owner_id_for_197(obj: tl.types.StarGiftUnique, _: SerializationContext) -> int | None:
    if not isinstance(obj.owner_id, tl.types.PeerUser):
        return None
    return obj.owner_id.user_id
