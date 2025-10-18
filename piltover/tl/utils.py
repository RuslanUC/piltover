from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . import TLObject


def is_content_related(obj: TLObject) -> bool:
    from . import core_types, Ping, Pong, HttpWait, MsgsAck
    return not isinstance(obj, (Ping, Pong, HttpWait, MsgsAck, core_types.MsgContainer, core_types.GzipPacked))


def is_id_content_related(obj_id: int) -> bool:
    from . import core_types, Ping, Pong, HttpWait, MsgsAck
    return obj_id not in {
        Ping.tlid(), Pong.tlid(), HttpWait.tlid(), MsgsAck.tlid(),
        core_types.MsgContainer.tlid(), core_types.GzipPacked.tlid(),
    }
