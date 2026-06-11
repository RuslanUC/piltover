from __future__ import annotations
from typing import TYPE_CHECKING
from piltover import tl

if TYPE_CHECKING:
    from piltover.tl.serialization_context import SerializationContext


def get_recent_message_interactions_fallback_for_133(obj: tl.types.stats.BroadcastStats, _: SerializationContext) -> list[tl.base.MessageInteractionCounters]:
    recent_interactions = []
    for interaction in obj.recent_posts_interactions:
        if not isinstance(interaction, tl.types.PostInteractionCountersMessage):
            continue
        recent_interactions.append(tl.types.MessageInteractionCounters_133(
            msg_id=interaction.msg_id,
            views=interaction.views,
            forwards=interaction.forwards,
        ))
    return recent_interactions
