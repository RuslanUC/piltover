from __future__ import annotations
from typing import TYPE_CHECKING
from piltover import tl

if TYPE_CHECKING:
    from piltover.tl.serialization_context import SerializationContext


def downgrade_reaction_for_138(obj: tl.types.MessagePeerReaction, _: SerializationContext) -> str:
    if isinstance(obj.reaction, tl.types.ReactionEmoji):
        return obj.reaction.emoticon
    return ""
