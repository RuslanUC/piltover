from pathlib import Path

from taskiq import TaskiqEvents
from tortoise import Tortoise

from piltover.app.handlers import register_handlers
from piltover.app.utils.config_helper import make_broker_from_config, make_message_broker_from_config
from piltover.cache import Cache
from piltover.config import SYSTEM_CONFIG, TORTOISE_ORM, WORKER_CONFIG
from piltover.utils.debug.tracing import Tracing
from piltover.worker import Worker


async def _run(*args, **kwargs) -> None:
    if SYSTEM_CONFIG.debug_tracing:
        Tracing.init(SYSTEM_CONFIG.debug_tracing.backend, zipkin_address=SYSTEM_CONFIG.debug_tracing.zipkin_address)
    await Tortoise.init(config=TORTOISE_ORM)


pubkey = Path(WORKER_CONFIG.pubkey_file)
if not pubkey.exists():
    raise RuntimeError(f"Public key at path \"{pubkey.absolute()}\" does not exist!")

broker = make_broker_from_config()
broker.add_event_handler(TaskiqEvents.WORKER_STARTUP, _run)

worker = Worker(
    data_dir=SYSTEM_CONFIG.data_dir,
    public_key=pubkey.read_text(),
    broker=broker,
    message_broker=make_message_broker_from_config(broker),
)

register_handlers(worker)

Cache.init(
    SYSTEM_CONFIG.cache.backend,
    endpoint=SYSTEM_CONFIG.cache.endpoint,
    port=SYSTEM_CONFIG.cache.port,
    db=SYSTEM_CONFIG.cache.db,
)
