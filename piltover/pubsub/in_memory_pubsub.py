import asyncio
from asyncio import Future

from piltover.pubsub.base import BaseOncePubSub


class InMemoryPubSub(BaseOncePubSub):
    def __init__(self) -> None:
        self.waiters: dict[str, Future] = {}

    async def startup(self) -> None:
        self.waiters.clear()

    async def shutdown(self) -> None:
        self.waiters.clear()

    async def notify(self, topic: str, data: bytes) -> None:
        if topic not in self.waiters:
            return

        self.waiters.pop(topic).set_result(data)

    async def listen(self, topic: str, timeout: float | None) -> bytes | None:
        if topic not in self.waiters:
            self.waiters[topic] = Future()

        if timeout is not None:
            try:
                return await asyncio.wait_for(self.waiters[topic], timeout)
            except TimeoutError:
                if topic in self.waiters:
                    del self.waiters[topic]
                return None

        return None
