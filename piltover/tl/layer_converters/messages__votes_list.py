from __future__ import annotations
from typing import TYPE_CHECKING
from piltover import tl

if TYPE_CHECKING:
    from piltover.tl.serialization_context import SerializationContext


def downgrade_votes_for_133(obj: tl.types.messages.VotesList, _: SerializationContext) -> list[tl.base.MessageUserVote]:
    votes = []
    for vote in obj.votes:
        peer = vote.peer
        if not isinstance(peer, tl.types.PeerUser):
            continue

        if isinstance(vote, tl.types.MessagePeerVote):
            votes.append(tl.types.MessageUserVote_133(
                user_id=peer.user_id,
                option=vote.option,
                date=vote.date,
            ))
        elif isinstance(vote, tl.types.MessagePeerVoteInputOption):
            votes.append(tl.types.MessageUserVoteInputOption_133(
                user_id=peer.user_id,
                date=vote.date,
            ))
        elif isinstance(vote, tl.types.MessagePeerVoteMultiple):
            votes.append(tl.types.MessageUserVoteMultiple_133(
                user_id=peer.user_id,
                options=vote.options,
                date=vote.date,
            ))

    return votes
