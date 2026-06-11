from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from piltover import tl
    from piltover.tl.serialization_context import SerializationContext


def downgrade_months_for_166(obj: tl.types.MessageMediaGiveaway, _: SerializationContext) -> int:
    if obj.months is not None:
        return obj.months
    return 0
