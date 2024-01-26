from __future__ import annotations
from contextvars import ContextVar
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from piltover.tl_new.tl_object import TLObject


class RequestContext:
    __slots__ = ("auth_key_id", "message_id", "session_id", "obj")

    def __init__(self, auth_key_id: int, message_id: int, session_id: int, obj: TLObject):
        self.auth_key_id = auth_key_id
        self.message_id = message_id
        self.session_id = session_id
        self.obj = obj


request_ctx: ContextVar[RequestContext] = ContextVar("request_ctx")

