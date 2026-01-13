from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import TypeVar, Generic, TYPE_CHECKING, Generator, Self, Any

if TYPE_CHECKING:
    from piltover.worker import Worker
    from piltover.storage import BaseStorage

T = TypeVar("T")


class RequestContext(Generic[T]):
    __slots__ = (
        "auth_key_id", "perm_auth_key_id", "message_id", "session_id", "obj", "auth_id", "user_id", "layer", "worker",
        "storage",
    )

    def __init__(
            self, auth_key_id: int, perm_auth_key_id: int | None, message_id: int, session_id: int, obj: T, layer: int,
            auth_id: int | None, user_id: int | None, worker: Worker, storage: BaseStorage,
    ):
        self.auth_key_id = auth_key_id
        self.perm_auth_key_id = perm_auth_key_id
        self.message_id = message_id
        self.session_id = session_id
        self.obj = obj
        self.auth_id = auth_id
        self.user_id = user_id
        self.layer = layer
        self.worker = worker
        self.storage = storage

    def __repr__(self) -> str:
        fields = ", ".join([f"{slot}={getattr(self, slot)!r}" for slot in self.__slots__])
        return f"{self.__class__.__name__}({fields})"


request_ctx: ContextVar[RequestContext] = ContextVar("request_ctx")


class SerializationContext(Generic[T]):
    __slots__ = ("auth_id", "user_id", "layer", "dont_format",)

    def __init__(self, auth_id: int, user_id: int, layer: int, dont_format: bool = False):
        self.auth_id = auth_id
        self.user_id = user_id
        self.layer = layer
        self.dont_format = dont_format

    @contextmanager
    def use(self) -> Generator[Self, None, None]:
        token = serialization_ctx.set(self)
        try:
            yield self
        finally:
            serialization_ctx.reset(token)


serialization_ctx: ContextVar[SerializationContext | None] = ContextVar("serialization_ctx", default=None)
