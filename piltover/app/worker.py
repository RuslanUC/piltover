from pathlib import Path

from taskiq import TaskiqEvents, AsyncBroker
from tortoise import Tortoise

from piltover.app.handlers import register_handlers
from piltover.cache import Cache
from piltover.config import SYSTEM_CONFIG, TORTOISE_ORM
from piltover.utils.debug.tracing import Tracing
from piltover.worker import Worker


class PiltoverWorker:
    def __init__(
            self, data_dir: Path,  pubkey: str | Path, rabbitmq_address: str | None = None,
            redis_address: str | None = None
    ):
        pubkey = Path(pubkey)
        if not pubkey.exists():
            raise RuntimeError(f"Public key at path \"{pubkey.absolute()}\" does not exist!")

        self._public_key = pubkey.read_text()

        self._worker = Worker(
            data_dir=data_dir,
            public_key=self._public_key,
            rabbitmq_address=rabbitmq_address,
            redis_address=redis_address,
        )

        register_handlers(self._worker)

        self._worker.broker.add_event_handler(TaskiqEvents.WORKER_STARTUP, self._run)

    @staticmethod
    async def _run(_):
        if SYSTEM_CONFIG.debug_tracing:
            Tracing.init(SYSTEM_CONFIG.debug_tracing.backend, zipkin_address=SYSTEM_CONFIG.debug_tracing.zipkin_address)
        await Tortoise.init(config=TORTOISE_ORM)

    def get_broker(self) -> AsyncBroker:
        return self._worker.broker


Cache.init(
    SYSTEM_CONFIG.cache.backend,
    endpoint=SYSTEM_CONFIG.cache.endpoint,
    port=SYSTEM_CONFIG.cache.port,
    db=SYSTEM_CONFIG.cache.db,
)
worker = PiltoverWorker(
    SYSTEM_CONFIG.data_dir,
    WORKER_CONFIG.pubkey_file,
    SYSTEM_CONFIG.rabbitmq_address,
    SYSTEM_CONFIG.redis_address,
)
broker = worker.get_broker()
