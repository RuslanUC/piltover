from __future__ import annotations

from datetime import UTC, datetime
from time import time
from typing import TypeVar

from loguru import logger
from taskiq import InMemoryBroker, TaskiqScheduler, ScheduleSource, ScheduledTask, AsyncBroker

from piltover.db.models import TaskIqScheduledMessage, TaskIqScheduledDeleteMessage

try:
    from taskiq_aio_pika import AioPikaBroker

    REMOTE_BROKER_SUPPORTED = True
except ImportError:
    AioPikaBroker = None
    REMOTE_BROKER_SUPPORTED = False

T = TypeVar("T")


class OrmDatabaseScheduleSource(ScheduleSource):
    @staticmethod
    async def _get_scheduled_to_send_messages() -> list[ScheduledTask]:
        current_minute = int(time())
        current_minute += (-current_minute % 60)
        scheduled_messages = await TaskIqScheduledMessage.filter(
            scheduled_time__lte=current_minute, start_processing__isnull=True,
        ).order_by("scheduled_time").limit(100)

        logger.trace(f"Got {len(scheduled_messages)} scheduled messages")

        scheduled_ids = [scheduled.id for scheduled in scheduled_messages]

        await TaskIqScheduledMessage.filter(id__in=scheduled_ids).update(start_processing=int(time()))

        return [
            ScheduledTask(
                task_name="send_scheduled",
                schedule_id=str(scheduled.id),
                labels={},
                args=[],
                kwargs={"message_id": scheduled.message_id},
                time=datetime.fromtimestamp(scheduled.scheduled_time, UTC),
            )
            for scheduled in scheduled_messages
        ]

    @staticmethod
    async def _get_scheduled_to_delete_messages() -> list[ScheduledTask]:
        current_minute = int(time())
        current_minute += (-current_minute % 60)
        scheduled_messages = await TaskIqScheduledDeleteMessage.filter(
            scheduled_for__lte=current_minute, start_processing__isnull=True,
        ).order_by("scheduled_for").limit(100)

        scheduled_ids = [scheduled.id for scheduled in scheduled_messages]

        await TaskIqScheduledMessage.filter(id__in=scheduled_ids).update(start_processing=int(time()))

        return [
            ScheduledTask(
                task_name="delete_scheduled",
                schedule_id=str(scheduled.id),
                labels={},
                args=[],
                kwargs={"message_id": scheduled.message_id},
                time=datetime.fromtimestamp(scheduled.scheduled_for, UTC),
            )
            for scheduled in scheduled_messages
        ]

    async def get_schedules(self) -> list[ScheduledTask]:
        return [
            *(await self._get_scheduled_to_send_messages()),
            *(await self._get_scheduled_to_delete_messages()),
        ]


class Scheduler:
    RMQ_HOST = "amqp://guest:guest@127.0.0.1:5672"

    def __init__(self, rabbitmq_address: str | None = RMQ_HOST, *, _broker: AsyncBroker | None = None):
        super().__init__()

        if not REMOTE_BROKER_SUPPORTED or rabbitmq_address is None:
            logger.info("Scheduler is initializing with InMemoryBroker")
            self.broker = _broker or InMemoryBroker()
        else:
            logger.info("Scheduler is initializing with AioPikaBroker")
            self.broker = AioPikaBroker(rabbitmq_address)

        self.scheduler = TaskiqScheduler(self.broker, sources=[OrmDatabaseScheduleSource()])
