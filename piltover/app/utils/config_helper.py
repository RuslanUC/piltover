from loguru import logger
from taskiq import AsyncBroker, InMemoryBroker, TaskiqEvents

from piltover._faster_taskiq_inmemory_result_backend import FasterInmemoryResultBackend
from piltover.config import SYSTEM_CONFIG
from piltover.message_brokers.base_broker import BaseMessageBroker, BrokerType
from piltover.message_brokers.in_memory_broker import InMemoryMessageBroker
from piltover.message_brokers.rabbitmq_broker import RabbitMqMessageBroker

try:
    from taskiq_aio_pika import AioPikaBroker
    from taskiq_redis import RedisAsyncResultBackend

    REMOTE_BROKER_SUPPORTED = True
except ImportError:
    AioPikaBroker = None
    RedisAsyncResultBackend = None
    REMOTE_BROKER_SUPPORTED = False


def make_broker_from_config() -> AsyncBroker:
    rabbitmq_address = SYSTEM_CONFIG.rabbitmq_address
    redis_address = SYSTEM_CONFIG.redis_address

    if not REMOTE_BROKER_SUPPORTED or rabbitmq_address is None or redis_address is None:
        logger.info("Using InMemoryBroker for taskiq")
        return InMemoryBroker(
            max_async_tasks=128,
            cast_types=False,
        ).with_result_backend(FasterInmemoryResultBackend())
    else:
        logger.info("Using AioPikaBroker + RedisAsyncResultBackend for taskiq")
        return AioPikaBroker(rabbitmq_address).with_result_backend(RedisAsyncResultBackend(redis_address))


def make_message_broker_from_config(broker: AsyncBroker | None) -> BaseMessageBroker:
    rabbitmq_address = SYSTEM_CONFIG.rabbitmq_address
    redis_address = SYSTEM_CONFIG.redis_address

    if not REMOTE_BROKER_SUPPORTED or rabbitmq_address is None or redis_address is None:
        logger.info("Using InMemoryMessageBroker")
        message_broker = InMemoryMessageBroker()
    else:
        logger.info("Using RabbitMqMessageBroker")
        message_broker = RabbitMqMessageBroker(BrokerType.WRITE, rabbitmq_address)

    if broker is not None:
        async def _broker_startup(*args, **kwargs) -> None:
            await message_broker.startup()

        async def _broker_shutdown(*args, **kwargs) -> None:
            await message_broker.shutdown()

        broker.add_event_handler(TaskiqEvents.WORKER_STARTUP, _broker_startup)
        broker.add_event_handler(TaskiqEvents.WORKER_SHUTDOWN, _broker_shutdown)

    return message_broker
