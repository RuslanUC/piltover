from __future__ import annotations
from typing import TYPE_CHECKING
from piltover import tl

if TYPE_CHECKING:
    from piltover.tl.serialization_context import SerializationContext


def downgrade_recent_voters_for_133(obj: tl.types.PollResults, _: SerializationContext) -> list[int] | None:
    if obj.recent_voters is None:
        return None
    return [
        voter.user_id
        for voter in obj.recent_voters
        if isinstance(voter, tl.types.PeerUser)
    ]
