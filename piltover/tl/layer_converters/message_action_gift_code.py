from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from piltover import tl
    from piltover.tl.serialization_context import SerializationContext


def downgrade_unclaimed_for_166(obj: tl.types.MessageActionGiftCode, _: SerializationContext) -> bool:
    return obj.unclaimed
