from asyncio import get_running_loop, Task
from io import BytesIO

from aio_pika import connect_robust, ExchangeType, Message as RmqMessage
from aio_pika.abc import AbstractChannel, DeliveryMode, AbstractQueue

from piltover.exceptions import Error
from piltover.message_brokers.base_broker import BaseMessageBroker, BrokerType, InternalMessages
from piltover.tl import TLObject


class RabbitMqMessageBroker(BaseMessageBroker):
    def __init__(self, broker_type: BrokerType, url: str, exchange_name: str = "piltover-internal-messages") -> None:
        super().__init__(broker_type)

        self._url = url
        self._listen_task: Task | None = None
        self._exchange_name = exchange_name

        self._write_conn = None
        self._write_channel: AbstractChannel | None = None
        self._read_conn = None
        self._read_channel: AbstractChannel | None = None

    async def startup(self) -> None:
        await super().startup()

        if BrokerType.WRITE in self.broker_type:
            self._write_conn = await connect_robust(self._url)
            self._write_channel = await self._write_conn.channel()
            await self._write_channel.declare_exchange(self._exchange_name, type=ExchangeType.TOPIC)

        if BrokerType.READ in self.broker_type:
            self._read_conn = await connect_robust(self._url)
            self._read_channel = await self._read_conn.channel()
            self._listen_task = get_running_loop().create_task(self._listen())

    async def shutdown(self) -> None:
        if self._write_channel:
            await self._write_channel.close()
        if self._read_channel:
            await self._read_channel.close()
        if self._write_conn:
            await self._write_conn.close()
        if self._read_conn:
            await self._read_conn.close()

        if self._listen_task:
            self._listen_task.cancel()

        await super().shutdown()

    async def send(self, message: InternalMessages) -> None:
        if BrokerType.WRITE not in self.broker_type:
            return

        rmq_message = RmqMessage(body=message.write(), delivery_mode=DeliveryMode.PERSISTENT)
        exchange = await self._write_channel.get_exchange(self._exchange_name, ensure=False)
        await exchange.publish(rmq_message, routing_key="piltover")

    async def _declare_queues(self, channel: AbstractChannel) -> AbstractQueue:
        await channel.declare_queue("piltover.dead_letter")
        queue = await channel.declare_queue(
            "piltover",
            arguments={
                "x-dead-letter-exchange": "",
                "x-dead-letter-routing-key": "piltover.dead_letter",
            },
        )

        await queue.bind(exchange=self._exchange_name, routing_key="piltover")
        return queue

    async def _listen(self) -> None:
        if BrokerType.READ not in self.broker_type:
            return

        queue = await self._declare_queues(self._read_channel)
        async with queue.iterator() as iterator:
            async for rmq_message in iterator:
                try:
                    message = TLObject.read(BytesIO(rmq_message.body))
                except Error:
                    continue

                await self.process_message(message)
