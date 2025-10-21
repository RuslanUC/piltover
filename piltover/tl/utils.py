from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . import TLObject


def is_content_related(obj: TLObject) -> bool:
    return is_id_content_related(obj.tlid())


def is_id_content_related(obj_id: int) -> bool:
    from . import core_types, Ping, Pong, HttpWait, MsgsAck, PingDelayDisconnect, MsgResendReq, DestroySession
    return obj_id not in {
        Ping.tlid(), PingDelayDisconnect.tlid(), Pong.tlid(), HttpWait.tlid(), MsgsAck.tlid(), MsgResendReq.tlid(),
        core_types.MsgContainer.tlid(), core_types.GzipPacked.tlid(), DestroySession.tlid(),
    }
