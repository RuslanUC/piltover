from __future__ import annotations

import asyncio
import base64
import os
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger
from taskiq import TaskiqEvents, AsyncBroker

from piltover.gateway.client import Client

try:
    from taskiq_aio_pika import AioPikaBroker
    from taskiq_redis import RedisAsyncResultBackend

    REMOTE_BROKER_SUPPORTED = True
except ImportError:
    AioPikaBroker = None
    RedisAsyncResultBackend = None
    REMOTE_BROKER_SUPPORTED = False

from piltover.message_brokers.base_broker import BrokerType
from piltover.message_brokers.rabbitmq_broker import RabbitMqMessageBroker

from piltover.auth_data import AuthData
from piltover.db.models import AuthKey
from piltover.session import SessionManager
from piltover.utils import gen_keys, get_public_key_fingerprint, load_private_key, load_public_key, background, Keys

if TYPE_CHECKING:
    from piltover.worker import Worker
    from piltover.scheduler import Scheduler


class Gateway:
    HOST = "0.0.0.0"
    PORT = 4430
    RMQ_HOST = "amqp://guest:guest@127.0.0.1:5672"
    REDIS_HOST = "redis://127.0.0.1"

    def __init__(
            self, data_dir: Path, host: str = HOST, port: int = PORT, server_keys: Keys | None = None,
            rabbitmq_address: str | None = RMQ_HOST, redis_address: str | None = REDIS_HOST,
            salt_key: bytes | None = None,
    ):
        self.data_dir = data_dir

        self.host = host
        self.port = port

        self.server_keys = server_keys
        if self.server_keys is None:
            self.server_keys = gen_keys()

        self.public_key = load_public_key(self.server_keys.public_key)
        self.private_key = load_private_key(self.server_keys.private_key)

        self.fingerprint: int = get_public_key_fingerprint(self.server_keys.public_key)
        self.fingerprint_signed: int = get_public_key_fingerprint(self.server_keys.public_key, True)

        self.clients: dict[str, Client] = {}

        if salt_key is None:
            salt_key = os.urandom(32)
            logger.info(f"Salt key is None, generating new one: {base64.b64encode(salt_key).decode('latin1')}")

        self.salt_key = salt_key

        self.worker: Worker | None
        self.broker: AsyncBroker | None
        self.scheduler: Scheduler | None

        if not REMOTE_BROKER_SUPPORTED or rabbitmq_address is None or redis_address is None:
            logger.info("rabbitmq_address or redis_address is None, falling back to worker broker")
            from piltover.worker import Worker
            from piltover.scheduler import Scheduler
            self.worker = Worker(data_dir, self.server_keys, None, None)
            self.broker = self.worker.broker
            self.scheduler = Scheduler(None, _broker=self.broker)
            self.message_broker = self.worker.message_broker
        else:
            logger.debug("Using AioPikaBroker + RedisAsyncResultBackend")
            self.worker = None
            self.scheduler = None
            self.broker = AioPikaBroker(rabbitmq_address).with_result_backend(RedisAsyncResultBackend(redis_address))
            self.message_broker = RabbitMqMessageBroker(BrokerType.READ, rabbitmq_address)
            self.broker.add_event_handler(TaskiqEvents.WORKER_STARTUP, self._broker_startup)
            self.broker.add_event_handler(TaskiqEvents.WORKER_STARTUP, self._broker_shutdown)

    async def _broker_startup(self, _) -> None:
        await self.message_broker.startup()
        SessionManager.set_broker(self.message_broker)

    async def _broker_shutdown(self, _) -> None:
        await self.message_broker.shutdown()

    @logger.catch
    async def accept_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        client = Client(server=self, reader=reader, writer=writer)
        background(client.worker())

    async def serve(self):
        await self.broker.startup()
        server = await asyncio.start_server(self.accept_client, self.host, self.port)
        async with server:
            await server.serve_forever()

    @staticmethod
    async def get_auth_data(auth_key_id: int) -> AuthData | None:
        logger.debug(f"Requested auth key: {auth_key_id}")
        return await AuthKey.get_auth_data(auth_key_id)
