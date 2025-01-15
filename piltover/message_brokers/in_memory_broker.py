from asyncio import Queue, get_running_loop, Task

from piltover.message_brokers.base_broker import BaseMessageBroker, BrokerType
from piltover.tl.types.internal import Message


class InMemoryMessageBroker(BaseMessageBroker):
    def __init__(self, broker_type: BrokerType = BrokerType.READ | BrokerType.WRITE) -> None:
        super().__init__(broker_type)

        self._messages: Queue[Message | None] | None = None
        self._listen_task: Task | None = None

    async def startup(self) -> None:
        print("startup")
        self._messages = Queue()
        self._listen_task = get_running_loop().create_task(self._listen())

    async def shutdown(self) -> None:
        await self._messages.put(None)
        self._messages = None
        print("shutdown")

    async def send(self, message: Message) -> None:
        await self._messages.put(message)

    async def _listen(self) -> None:
        while self._messages is not None:
            message = await self._messages.get()
            if message is None:
                break

            await self.process_message(message)
