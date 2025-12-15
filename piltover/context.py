from __future__ import annotations

from contextvars import ContextVar, Token
from typing import TypeVar, Generic, TYPE_CHECKING

if TYPE_CHECKING:
    from piltover.worker import Worker
    from piltover.storage import BaseStorage

T = TypeVar("T")


class RequestContext(Generic[T]):
    __slots__ = (
        "auth_key_id", "perm_auth_key_id", "message_id", "session_id", "obj", "auth_id", "user_id", "layer", "worker",
        "storage",
        "_parent_token",
    )

    def __init__(
            self, auth_key_id: int, perm_auth_key_id: int | None, message_id: int, session_id: int, obj: T, layer: int,
            auth_id: int | None, user_id: int | None, worker: Worker, storage: BaseStorage,
            *, _parent_token: Token[RequestContext[T]] | None = None
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

        self._parent_token: Token[RequestContext[T]] | None = _parent_token

    def clone(self, **kwargs) -> RequestContext:
        values = {slot: getattr(self, slot) for slot in self.__slots__}
        values |= kwargs
        return self.__class__(**values)

    def __repr__(self) -> str:
        fields = ", ".join([f"{slot}={getattr(self, slot)!r}" for slot in self.__slots__])
        return f"{self.__class__.__name__}({fields})"

    @staticmethod
    def save(**kwargs) -> RequestContext:
        old_ctx = request_ctx.get()
        new_ctx = old_ctx.clone(_parent=old_ctx, **kwargs)
        new_ctx._parent_token = request_ctx.set(new_ctx)
        return new_ctx

    @staticmethod
    def restore() -> RequestContext:
        old_token = request_ctx.get()._parent_token
        if old_token is None:
            raise RuntimeError("Context has no parent context to restore.")

        request_ctx.reset(old_token)
        return request_ctx.get(None)


request_ctx: ContextVar[RequestContext] = ContextVar("request_ctx")


class SerializationContext(Generic[T]):
    __slots__ = ("auth_id", "user_id", "dont_format",)

    def __init__(self, auth_id: int | None, user_id: int | None, dont_format: bool = False):
        self.auth_id = auth_id
        self.user_id = user_id
        self.dont_format = dont_format


serialization_ctx: ContextVar[SerializationContext | None] = ContextVar("serialization_ctx", default=None)
