from __future__ import annotations

from abc import ABC, abstractmethod
from typing import NamedTuple, TYPE_CHECKING

from piltover.auth_data import AuthData

if TYPE_CHECKING:
    from piltover.session import Session


class SessionKey(NamedTuple):
    key_id: int
    session_id: int


class MessagePullResult(NamedTuple):
    session_key: SessionKey
    message_id: int
    seq_no: int
    data: bytes


class BaseSessionStorage(ABC):
    async def start(self) -> None:
        ...

    async def stop(self) -> None:
        ...

    @abstractmethod
    async def get_session(self, session_id: int, auth_data: AuthData) -> Session:
        ...

    @abstractmethod
    async def save_session(self, session: Session) -> None:
        ...

    @abstractmethod
    async def destroy_session(self, session_key: SessionKey) -> None:
        ...

    @abstractmethod
    async def push(self, session_key: SessionKey, message_id: int, seq_no: int, data: bytes) -> None:
        ...

    @abstractmethod
    async def pull(self, sessions: dict[SessionKey, int], timeout: float = 0.1) -> list[MessagePullResult]:
        ...

    @abstractmethod
    async def ack(self, session_key: SessionKey, message_ids: list[int]) -> None:
        ...


# TODO: add redis storage
