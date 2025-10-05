from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . import TLObject


def is_content_related(obj: TLObject) -> bool:
    from . import core_types, Ping, Pong, HttpWait, MsgsAck
    return not isinstance(obj, (Ping, Pong, HttpWait, MsgsAck, core_types.MsgContainer, core_types.GzipPacked))
