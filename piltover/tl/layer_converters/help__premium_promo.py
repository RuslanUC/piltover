from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from piltover import tl
    from piltover.tl.serialization_context import SerializationContext


def get_currency_fallback_for_143(_1: tl.types.help.PremiumPromo, _2: SerializationContext) -> str:
    return "USD"


def get_monthly_amount_fallback_for_143(_1: tl.types.help.PremiumPromo, _2: SerializationContext) -> int:
    return 0
