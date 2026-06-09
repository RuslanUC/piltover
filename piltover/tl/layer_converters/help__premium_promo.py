from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from piltover import tl


def get_currency_fallback_for_143(obj: tl.types.help._PremiumPromoDowngradable) -> str:
    return "USD"


def get_monthly_amount_fallback_for_143(obj: tl.types.help._PremiumPromoDowngradable) -> int:
    return 0
