from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from piltover import tl
    from piltover.tl.serialization_context import SerializationContext


def downgrade_title_for_158(obj: tl.types.chatlists.ChatlistInvite, ctx: SerializationContext) -> str:
    return obj.title.text
