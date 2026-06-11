from __future__ import annotations
from typing import TYPE_CHECKING
from piltover import tl

if TYPE_CHECKING:
    from piltover.tl.serialization_context import SerializationContext


def downgrade_available_reactions_for_136(obj: tl.types.ChatFull, _: SerializationContext) -> list[str] | None:
    if not isinstance(obj.available_reactions, tl.types.ChatReactionsSome):
        return []
    return [
        reaction.emoticon
        for reaction in obj.available_reactions.reactions
        if isinstance(reaction, tl.types.ReactionEmoji)
    ]
