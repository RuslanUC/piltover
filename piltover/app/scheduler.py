import asyncio

import uvloop
from tortoise import Tortoise

from piltover.config import SYSTEM_CONFIG, TORTOISE_ORM
from piltover.messaging import NatsMessaging
from piltover.scheduler import Scheduler


async def main() -> None:
    if SYSTEM_CONFIG.nats_address is not None:
        messaging = NatsMessaging(SYSTEM_CONFIG.nats_address)
    else:
        raise ValueError("To run scheduler separately from app, `nats_address` should be set!")

    scheduler = Scheduler(messaging=messaging)

    await Tortoise.init(config=TORTOISE_ORM)
    await messaging.start()

    asyncio.get_running_loop().run_until_complete(scheduler.run())


if __name__ == "__main__":
    try:
        uvloop.run(main())
    except KeyboardInterrupt:
        pass
