from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from piltover import tl
    from piltover.tl.serialization_context import SerializationContext


def downgrade_current_balance_for_182(obj: tl.types.StarsRevenueStatus, _: SerializationContext) -> int:
    return obj.current_balance.amount


def downgrade_available_balance_for_182(obj: tl.types.StarsRevenueStatus, _: SerializationContext) -> int:
    return obj.available_balance.amount


def downgrade_overall_revenue_for_182(obj: tl.types.StarsRevenueStatus, _: SerializationContext) -> int:
    return obj.overall_revenue.amount
