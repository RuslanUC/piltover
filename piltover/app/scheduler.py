from taskiq import TaskiqEvents, TaskiqScheduler
from tortoise import Tortoise

from piltover.app.utils.config_helper import make_broker_from_config
from piltover.config import TORTOISE_ORM
from piltover.scheduler import OrmDatabaseScheduleSource


async def _init_db(*args, **kwargs) -> None:
    await Tortoise.init(config=TORTOISE_ORM)


broker = make_broker_from_config()
broker.add_event_handler(TaskiqEvents.WORKER_STARTUP, _init_db)
scheduler = TaskiqScheduler(broker, sources=[OrmDatabaseScheduleSource()])
