from __future__ import annotations
from typing import TYPE_CHECKING
from piltover import tl

if TYPE_CHECKING:
    from piltover.tl.serialization_context import SerializationContext


def get_reply_to_msg_id_fallback_for_133(obj: tl.types.DraftMessage, _: SerializationContext) -> int | None:
    if isinstance(obj.reply_to, (
            tl.types.InputReplyToMessage, tl.types.InputReplyToMessage_160, tl.types.InputReplyToMessage_166
    )):
        return obj.reply_to.reply_to_msg_id
    return None

