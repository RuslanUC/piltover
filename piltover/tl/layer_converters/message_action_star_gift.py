from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from piltover import tl
    from piltover.tl.serialization_context import SerializationContext


def downgrade_convert_stars_for_189(obj: tl.types.MessageActionStarGift, _: SerializationContext) -> int:
    if obj.convert_stars is not None:
        return obj.convert_stars
    return 0
