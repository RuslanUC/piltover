from __future__ import annotations

from contextvars import ContextVar
from typing import TypeVar, Generic


T = TypeVar("T")


class RequestContext(Generic[T]):
    __slots__ = ("auth_key_id", "message_id", "session_id", "obj", "client")

    def __init__(self, auth_key_id: int, message_id: int, session_id: int, obj: T, client):
        self.auth_key_id = auth_key_id
        self.message_id = message_id
        self.session_id = session_id
        self.obj = obj
        self.client = client


request_ctx: ContextVar[RequestContext] = ContextVar("request_ctx")
