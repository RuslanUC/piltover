from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING, TypeVar, Generic

if TYPE_CHECKING:
    from piltover.db.models import User

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


class SerializationContext:
    __slots__ = ("user", "layer")

    def __init__(self, user: User | None, layer: int):
        self.user = user
        self.layer = layer


serialization_ctx: ContextVar[SerializationContext] = ContextVar("request_ctx", default=SerializationContext(None, 167))


@contextmanager
def rewrite_ctx(ctx: ContextVar, **kwargs):
    cls = type(ctx.get())
    old_ctx = ctx.set(cls(**kwargs))
    yield
    ctx.reset(old_ctx)
