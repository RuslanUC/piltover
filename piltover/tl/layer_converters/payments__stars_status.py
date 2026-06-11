from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from piltover import tl
    from piltover.tl.serialization_context import SerializationContext


def downgrade_balance_for_181(obj: tl.types.payments.StarsStatus, _: SerializationContext) -> int:
    return obj.balance.amount


def downgrade_history_for_181(obj: tl.types.payments.StarsStatus, _: SerializationContext) -> list[tl.base.StarsTransaction]:
    if obj.history is not None:
        return obj.history
    return []
