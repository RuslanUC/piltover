from __future__ import annotations
from typing import TYPE_CHECKING
from piltover import tl

if TYPE_CHECKING:
    from piltover.tl.serialization_context import SerializationContext


def get_chosen_fallback_for_136(obj: tl.types.ReactionCount, _: SerializationContext) -> bool:
    return obj.chosen_order is not None


def downgrade_reaction_for_136(obj: tl.types.ReactionCount, _: SerializationContext) -> str:
    if isinstance(obj.reaction, tl.types.ReactionEmoji):
        return obj.reaction.emoticon
    return ""
