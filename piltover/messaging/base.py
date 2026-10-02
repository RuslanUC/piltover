from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, Awaitable
from nats.aio.msg import Msg


class BaseSubscription(ABC):
    __slots__ = ()

    @abstractmethod
    async def unsubscribe(self, wait_for_pending: bool = False) -> None:
        ...

    @abstractmethod
    async def receive(self, timeout: float) -> BaseMessage:
        ...


class BaseMessage(ABC):
    __slots__ = ("data",)

    def __init__(self, data: bytes) -> None:
        self.data = data

    @abstractmethod
    async def respond(self, payload: bytes) -> None:
        ...


class BaseMessaging(ABC):
    __slots__ = ()

    @abstractmethod
    async def start(self) -> None:
        ...

    @abstractmethod
    async def stop(self) -> None:
        ...

    @abstractmethod
    async def publish(self, subject: str, payload: bytes) -> None:
        ...

    @abstractmethod
    async def request(self, subject: str, payload: bytes, timeout: float) -> BaseMessage:
        ...

    @abstractmethod
    async def subscribe(
            self,
            subject: str,
            callback: Callable[[BaseMessage], Awaitable[None]] | None = None,
            queue: str = "",
            **backend_args,
    ) -> BaseSubscription:
        ...
