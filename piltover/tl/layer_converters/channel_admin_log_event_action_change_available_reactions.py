from __future__ import annotations
from typing import TYPE_CHECKING
from piltover import tl
if TYPE_CHECKING:
    from piltover.tl.serialization_context import SerializationContext


def downgrade_prev_value_for_136(obj: tl.types.ChannelAdminLogEventActionChangeAvailableReactions, _: SerializationContext) -> list[str]:
    if not isinstance(obj.prev_value, tl.types.ChatReactionsSome):
        return []
    return [
        reaction.emoticon
        for reaction in obj.prev_value.reactions
        if isinstance(reaction, tl.types.ReactionEmoji)
    ]


def downgrade_new_value_for_136(obj: tl.types.ChannelAdminLogEventActionChangeAvailableReactions, _: SerializationContext) -> list[str]:
    if not isinstance(obj.new_value, tl.types.ChatReactionsSome):
        return []
    return [
        reaction.emoticon
        for reaction in obj.new_value.reactions
        if isinstance(reaction, tl.types.ReactionEmoji)
    ]
