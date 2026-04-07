from taskiq import TaskiqEvents, AsyncBroker, TaskiqScheduler
from tortoise import Tortoise

from piltover.config import TORTOISE_ORM, SYSTEM_CONFIG
from piltover.scheduler import Scheduler


class PiltoverScheduler:
    def __init__(self, rabbitmq_address: str | None = None):
        self._scheduler = Scheduler(rabbitmq_address=rabbitmq_address)
        self._scheduler.broker.add_event_handler(TaskiqEvents.WORKER_STARTUP, self._run)

    @staticmethod
    async def _run():
        await Tortoise.init(config=TORTOISE_ORM)

    def get_broker(self) -> AsyncBroker:
        return self._scheduler.broker

    def get_scheduler(self) -> TaskiqScheduler:
        return self._scheduler.scheduler


_scheduler = PiltoverScheduler(SYSTEM_CONFIG.rabbitmq_address)
broker = _scheduler.get_broker()
scheduler = _scheduler.get_scheduler()
