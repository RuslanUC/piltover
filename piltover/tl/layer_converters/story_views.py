from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from piltover import tl
    from piltover.tl.serialization_context import SerializationContext


def downgrade_reactions_count_for_161(obj: tl.types.StoryViews, _: SerializationContext) -> int:
    if obj.reactions_count is not None:
        return obj.reactions_count
    return 0
