from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from piltover import tl
    from piltover.tl.serialization_context import SerializationContext


def get_current_balance_fallback_for_177(obj: tl.types.stats.BroadcastRevenueStats, _: SerializationContext) -> int:
    return obj.balances.current_balance


def get_available_balance_fallback_for_177(obj: tl.types.stats.BroadcastRevenueStats, _: SerializationContext) -> int:
    return obj.balances.available_balance


def get_overall_revenue_fallback_for_177(obj: tl.types.stats.BroadcastRevenueStats, _: SerializationContext) -> int:
    return obj.balances.overall_revenue
