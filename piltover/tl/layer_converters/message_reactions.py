from __future__ import annotations
from typing import TYPE_CHECKING
from piltover import tl

if TYPE_CHECKING:
    from piltover.tl.serialization_context import SerializationContext


def get_recent_reactons_fallback_for_136(obj: tl.types.MessageReactions, _: SerializationContext) -> list[tl.base.MessageUserReaction] | None:
    if obj.recent_reactions is None:
        return None

    recent = []
    for reaction in obj.recent_reactions:
        peer = reaction.peer_id
        if not isinstance(peer, tl.types.PeerUser):
            continue

        if isinstance(obj, tl.types.MessagePeerReaction_138):
            reaction_emoji = obj.reaction
        elif isinstance(obj, (tl.types.MessagePeerReaction_145, tl.types.MessagePeerReaction)):
            if isinstance(obj.reaction, tl.types.ReactionEmoji):
                reaction_emoji = obj.reaction.emoticon
            else:
                continue
        else:
            continue

        recent.append(tl.types.MessageUserReaction_136(
            user_id=peer.user_id,
            reaction=reaction_emoji
        ))

    return recent
