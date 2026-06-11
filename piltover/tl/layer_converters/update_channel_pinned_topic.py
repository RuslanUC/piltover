from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from piltover import tl
    from piltover.tl.serialization_context import SerializationContext


def downgrade_topic_id_for_148(obj: tl.types.UpdateChannelPinnedTopic, _: SerializationContext) -> int | None:
    return obj.topic_id
