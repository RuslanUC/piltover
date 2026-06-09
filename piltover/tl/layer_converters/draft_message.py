from __future__ import annotations
from piltover import tl


def get_reply_to_msg_id_fallback_for_133(obj: tl.types._root._DraftMessageDowngradable) -> int | None:
    if isinstance(obj.reply_to, (
            tl.types.InputReplyToMessage, tl.types.InputReplyToMessage_160, tl.types.InputReplyToMessage_166,
    )):
        return obj.reply_to.reply_to_msg_id
    return None
