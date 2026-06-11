from __future__ import annotations
from typing import TYPE_CHECKING
from piltover import tl

if TYPE_CHECKING:
    from piltover.tl.serialization_context import SerializationContext


def get_user_stories_fallback_for_160(obj: tl.types.stories.AllStories, _: SerializationContext) -> list[tl.base.UserStories]:
    user_stories = []
    for story in obj.peer_stories:
        peer = story.peer
        if not isinstance(peer, tl.types.PeerUser):
            continue
        user_stories.append(tl.types.UserStories_160(
            user_id=peer.user_id,
            max_read_id=story.max_read_id,
            stories=story.stories,
        ))

    return user_stories
