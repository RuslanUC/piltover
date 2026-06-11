from __future__ import annotations
from typing import TYPE_CHECKING
from piltover import tl

if TYPE_CHECKING:
    from piltover.tl.serialization_context import SerializationContext


def get_option_fallback_for_181(_1: tl.types.InputInvoiceStars, _2: SerializationContext) -> tl.types.StarsTopupOption:
    return tl.types.StarsTopupOption(
        stars=1,
        currency="USD",
        amount=0,
    )
