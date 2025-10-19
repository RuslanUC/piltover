import argparse
from os import getenv
from types import SimpleNamespace

from taskiq import TaskiqEvents, AsyncBroker, TaskiqScheduler
from tortoise import Tortoise

from piltover.scheduler import Scheduler

DB_CONNECTION_STRING = getenv("DB_CONNECTION_STRING", "sqlite://data/secrets/piltover.db")


class ArgsNamespace(SimpleNamespace):
    rabbitmq_address: str | None


class PiltoverScheduler:
    def __init__(self, rabbitmq_address: str | None = None):
        self._scheduler = Scheduler(rabbitmq_address=rabbitmq_address)
        self._scheduler.broker.add_event_handler(TaskiqEvents.WORKER_STARTUP, self._run)

    @staticmethod
    async def _run():
        await Tortoise.init(
            db_url=DB_CONNECTION_STRING,
            modules={"models": ["piltover.db.models"]},
        )

    def get_broker(self) -> AsyncBroker:
        return self._scheduler.broker

    def get_scheduler(self) -> TaskiqScheduler:
        return self._scheduler.scheduler


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--rabbitmq-address", type=str, required=False,
                        help="Address of rabbitmq server in \"amqp://user:password@host:port\" format",
                        default=None)
    args = parser.parse_args(namespace=ArgsNamespace())
else:
    args = ArgsNamespace(rabbitmq_address=None)

args.fill_defaults()

_scheduler = PiltoverScheduler(args.rabbitmq_address)
broker = _scheduler.get_broker()
scheduler = _scheduler.get_scheduler()
