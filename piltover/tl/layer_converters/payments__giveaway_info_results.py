from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from piltover import tl
    from piltover.tl.serialization_context import SerializationContext


def downgrade_gift_code_slug_for_166(obj: tl.types.payments.GiveawayInfoResults, _: SerializationContext) -> str | None:
    return obj.gift_code_slug


def downgrade_activated_count_for_166(obj: tl.types.payments.GiveawayInfoResults, _: SerializationContext) -> int:
    if obj.activated_count is not None:
        return obj.activated_count
    return 0
