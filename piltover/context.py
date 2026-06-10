from __future__ import annotations

from contextvars import ContextVar
from typing import TypeVar, Generic, TYPE_CHECKING

from piltover.tl import TLObject
from piltover.tl.types.internal import NeedsContextValues

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


class NeedContextValuesContext:
    __slots__ = (
        "poll_answers", "chat_participants", "channel_participants", "users", "channel_messages", "stickersets",
    )

    def __init__(self) -> None:
        self.poll_answers: set[int] = set()
        self.chat_participants: set[int] = set()
        self.channel_participants: set[int] = set()
        self.users: set[int] = set()
        self.channel_messages: set[int] = set()

    def any(self) -> bool:
        return (
                bool(self.poll_answers)
                or bool(self.chat_participants)
                or bool(self.channel_participants)
                or bool(self.users)
                or bool(self.channel_messages)
        )

    def to_tl(self, obj: TLObject) -> NeedsContextValues:
        return NeedsContextValues(
            obj=obj,
            poll_answers=list(self.poll_answers) if self.poll_answers else None,
            chat_participants=list(self.chat_participants) if self.chat_participants else None,
            channel_participants=list(self.channel_participants) if self.channel_participants else None,
            users=list(self.users) if self.users else None,
            channel_messages=list(self.channel_messages) if self.channel_messages else None,
        )
