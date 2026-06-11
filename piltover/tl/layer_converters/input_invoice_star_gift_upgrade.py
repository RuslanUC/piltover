from __future__ import annotations
from typing import TYPE_CHECKING
from piltover import tl

if TYPE_CHECKING:
    from piltover.tl.serialization_context import SerializationContext


def get_msg_id_fallback_for_196(obj: tl.types.InputInvoiceStarGiftUpgrade, _: SerializationContext) -> int:
    if isinstance(obj.stargift, tl.types.InputSavedStarGiftUser):
        return obj.stargift.msg_id
    return 0
