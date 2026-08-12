import asyncio
from pathlib import Path

import uvloop
from tortoise import Tortoise

from piltover.app.handlers import register_handlers
from piltover.cache import Cache
from piltover.config import SYSTEM_CONFIG, TORTOISE_ORM, WORKER_CONFIG
from piltover.utils.debug.tracing import Tracing
from piltover.worker import Worker


async def main() -> None:
    pubkey = Path(WORKER_CONFIG.pubkey_file)
    if not pubkey.exists():
        raise RuntimeError(f"Public key at path \"{pubkey.absolute()}\" does not exist!")

    worker = Worker(
        data_dir=SYSTEM_CONFIG.data_dir,
        public_key=pubkey.read_text(),
    )

    register_handlers(worker)

    Cache.init(
        SYSTEM_CONFIG.cache.backend,
        endpoint=SYSTEM_CONFIG.cache.endpoint,
        port=SYSTEM_CONFIG.cache.port,
        db=SYSTEM_CONFIG.cache.db,
    )

    if SYSTEM_CONFIG.debug_tracing:
        Tracing.init(SYSTEM_CONFIG.debug_tracing.backend, zipkin_address=SYSTEM_CONFIG.debug_tracing.zipkin_address)
    await Tortoise.init(config=TORTOISE_ORM)

    await worker.start()


if __name__ == "__main__":
    with asyncio.Runner(loop_factory=uvloop.new_event_loop) as runner:
        runner.run(main())
