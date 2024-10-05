from __future__ import annotations

from . import TLObject


def is_content_related(obj: TLObject) -> bool:
    from . import core_types, Ping, Pong, HttpWait, MsgsAck
    return isinstance(obj, (Ping, Pong, HttpWait, MsgsAck, core_types.MsgContainer))
