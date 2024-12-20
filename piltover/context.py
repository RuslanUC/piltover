from __future__ import annotations

from contextvars import ContextVar
from typing import TypeVar, Generic, TYPE_CHECKING

if TYPE_CHECKING:
    from .server import Client


T = TypeVar("T")


class RequestContext(Generic[T]):
    __slots__ = ("auth_key_id", "message_id", "session_id", "obj", "client")

    def __init__(self, auth_key_id: int, message_id: int, session_id: int, obj: T, client: Client):
        self.auth_key_id = auth_key_id
        self.message_id = message_id
        self.session_id = session_id
        self.obj = obj
        self.client = client

    def clone(self, **kwargs) -> RequestContext:
        values = {slot: getattr(self, slot) for slot in self.__slots__}
        values |= kwargs
        return self.__class__(**values)

    def __repr__(self) -> str:
        fields = ", ".join([f"{slot}={getattr(self, slot)!r}" for slot in self.__slots__])
        return f"{self.__class__.__name__}({fields})"


request_ctx: ContextVar[RequestContext] = ContextVar("request_ctx")
