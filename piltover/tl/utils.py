from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . import TLObject


def is_content_related(obj: TLObject) -> bool:
    return not is_id_strictly_not_content_related(obj.tlid())


def is_id_strictly_not_content_related(obj_id: int) -> bool:
    from . import core_types, MsgsAck
    # TODO: msg_copy#e06046b2
    return obj_id in {
        MsgsAck.tlid(), core_types.MsgContainer.tlid(),
        # TODO: IS GZIP-PACKED CONTENT RELATED OR NOT ?????
        # core_types.GzipPacked.tlid(),
    }


def is_id_strictly_content_related(obj_id: int) -> bool:
    from .core_types import RpcResult
    return obj_id == RpcResult.tlid()
