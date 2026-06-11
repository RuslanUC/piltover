from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from piltover import tl
    from piltover.tl.serialization_context import SerializationContext


def get_next_phone_login_date_fallback_for_145(_1: tl.types.auth.SentCodeTypeEmailCode, _2: SerializationContext) -> int | None:
    return False
