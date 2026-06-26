from abc import ABC, abstractmethod
from typing import NamedTuple


class QueueKey(NamedTuple):
    key_id: int
    session_id: int


class MessagePullResult(NamedTuple):
    session_key: QueueKey
    message_id: int
    seq_no: int
    data: bytes


# TODO: rename to BaseMessageStorage
class BaseMessageQueue(ABC):
    async def start(self) -> None:
        ...

    async def stop(self) -> None:
        ...

    @abstractmethod
    async def push(self, session_key: QueueKey, message_id: int, seq_no: int, data: bytes) -> None:
        ...

    @abstractmethod
    async def pull(self, sessions: dict[QueueKey, int], timeout: float = 0.1) -> list[MessagePullResult]:
        ...

    @abstractmethod
    async def ack(self, session_key: QueueKey, message_ids: list[int]) -> None:
        ...


# TODO: add redis storage
