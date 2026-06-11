from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from piltover import tl
    from piltover.tl.serialization_context import SerializationContext


def downgrade_extended_media_for_147(obj: tl.types.UpdateMessageExtendedMedia, _: SerializationContext) -> tl.base.MessageExtendedMedia:
    return obj.extended_media[0]
