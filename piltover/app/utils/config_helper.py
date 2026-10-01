from loguru import logger
from taskiq import AsyncBroker, InMemoryBroker

from piltover._faster_taskiq_inmemory_result_backend import FasterInmemoryResultBackend
from piltover.config import SYSTEM_CONFIG

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

