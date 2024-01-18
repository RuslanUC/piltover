from __future__ import annotations

import piltover.tl_new as tl_new
from piltover.tl_new import core_types


def is_content_related(obj: tl_new.TLObject) -> bool:
    return isinstance(obj, (tl_new.Ping, tl_new.Pong, tl_new.HttpWait, tl_new.MsgsAck, core_types.MsgContainer))
