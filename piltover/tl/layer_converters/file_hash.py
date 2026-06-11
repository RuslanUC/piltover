from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from piltover import tl
    from piltover.tl.serialization_context import SerializationContext


def downgrade_offset_for_133(obj: tl.types.FileHash, _: SerializationContext) -> int:
    return obj.offset
