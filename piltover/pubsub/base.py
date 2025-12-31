from abc import ABC, abstractmethod
from typing import overload


class BaseOncePubSub(ABC):
    @abstractmethod
    async def startup(self) -> None:
        ...

    @abstractmethod
    async def shutdown(self) -> None:
        ...

    @abstractmethod
    async def notify(self, topic: str, data: bytes) -> None:
        ...

    @overload
    async def listen(self, topic: str, timeout: float) -> bytes:
        ...

    @overload
    async def listen(self, topic: str, timeout: None) -> None:
        ...

    @overload
    async def listen(self, topic: str, timeout: float | None) -> bytes | None:
        ...

    @abstractmethod
    async def listen(self, topic: str, timeout: float | None) -> bytes | None:
        ...
