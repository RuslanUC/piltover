from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from piltover import tl
    from piltover.tl.serialization_context import SerializationContext


def get_animated_fallback_for_133(_1: tl.types.StickerSet, _2: SerializationContext) -> bool:
    return False


def get_videos_fallback_for_133(_1: tl.types.StickerSet, _2: SerializationContext) -> bool:
    return False
