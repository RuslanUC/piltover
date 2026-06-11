from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from piltover import tl
    from piltover.tl.serialization_context import SerializationContext


def downgrade_chat_id_for_133(obj: tl.types.UpdateGroupCall, _: SerializationContext) -> int:
    if obj.chat_id is not None:
        return obj.chat_id
    return 0
