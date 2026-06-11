from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from piltover import tl
    from piltover.tl.serialization_context import SerializationContext


def get_background_emoji_id_fallback_for_166(obj: tl.types.User, _: SerializationContext) -> int | None:
    if obj.color is None:
        return None
    return obj.color.background_emoji_id


def downgrade_color_for_166(obj: tl.types.User, _: SerializationContext) -> int | None:
    if obj.color is None:
        return None
    return obj.color.color
