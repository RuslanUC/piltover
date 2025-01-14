from __future__ import annotations

from contextvars import ContextVar
from typing import TypeVar, Generic

T = TypeVar("T")


class RequestContext(Generic[T]):
    __slots__ = ("auth_key_id", "message_id", "session_id", "obj", "_parent")

    def __init__(
            self, auth_key_id: int, message_id: int, session_id: int, obj: T, *, _parent: RequestContext | None = None
    ):
        self.auth_key_id = auth_key_id
        self.message_id = message_id
        self.session_id = session_id
        self.obj = obj

        self._parent: RequestContext[T] | None = _parent

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
        request_ctx.set(new_ctx)

        return new_ctx

    @staticmethod
    def restore() -> RequestContext:
        old_ctx = request_ctx.get()._parent
        if old_ctx is None:
            raise RuntimeError("Context has no parent context to restore.")

        request_ctx.set(old_ctx)
        return old_ctx


request_ctx: ContextVar[RequestContext] = ContextVar("request_ctx")
