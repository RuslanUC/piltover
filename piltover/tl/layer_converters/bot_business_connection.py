from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from piltover import tl
    from piltover.tl.serialization_context import SerializationContext


def get_can_reply_fallback_for_177(obj: tl.types.BotBusinessConnection, _: SerializationContext) -> bool:
    if obj.rights is None:
        return False
    return obj.rights.reply
