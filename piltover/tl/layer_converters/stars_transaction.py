from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from piltover import tl
    from piltover.tl.serialization_context import SerializationContext


def downgrade_stars_for_181(obj: tl.types.StarsTransaction, _: SerializationContext) -> int:
    return obj.stars.amount
