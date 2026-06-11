from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from piltover import tl
    from piltover.tl.serialization_context import SerializationContext


def downgrade_reply_to_msg_id_for_133(obj: tl.types.MessageReplyHeader, _: SerializationContext) -> int:
    if obj.reply_to_msg_id is not None:
        return obj.reply_to_msg_id
    return 0
