from __future__ import annotations

from datetime import UTC, datetime
from time import time
from typing import TypeVar

from loguru import logger
from taskiq import InMemoryBroker, TaskiqScheduler, ScheduleSource, ScheduledTask, AsyncBroker

from piltover.db.enums import TaskIqScheduledState
from piltover.db.models import TaskIqScheduledMessage, TaskIqScheduledDeleteMessage
from piltover.tl.functions.internal import SendScheduledMessage, DeleteScheduledMessage, CallRpcInternal

try:
    from taskiq_aio_pika import AioPikaBroker
except ImportError:
    AioPikaBroker = None

T = TypeVar("T")


class OrmDatabaseScheduleSource(ScheduleSource):
    @staticmethod
    async def _reset_scheduled_to_send_stuck_messages() -> None:
        await TaskIqScheduledMessage.filter(
            state__not=TaskIqScheduledState.SCHEDULED, state_updated_at__lte=int(time() - 60 * 5)
        ).update(state=TaskIqScheduledState.SCHEDULED, state_updated_at=int(time()))

    @staticmethod
    async def _get_scheduled_to_send_messages() -> list[ScheduledTask]:
        scheduled_messages = await TaskIqScheduledMessage.filter(
            scheduled_time__lte=int(time()), state=TaskIqScheduledState.SCHEDULED,
        ).order_by("scheduled_time").limit(100)

        logger.trace("Got {count} scheduled messages", count=len(scheduled_messages))

        scheduled_ids = [scheduled.id for scheduled in scheduled_messages]

        await TaskIqScheduledMessage.filter(id__in=scheduled_ids).update(
            state=TaskIqScheduledState.SENT, state_updated_at=int(time())
        )

        return [
            ScheduledTask(
                task_name="handle_tl_rpc_internal",
                schedule_id=str(scheduled.id),
                labels={},
                args=[],
                kwargs={
                    "call": CallRpcInternal(obj=SendScheduledMessage(message_id=scheduled.message_id)).write().hex(),
                },
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

        await TaskIqScheduledDeleteMessage.filter(id__in=scheduled_ids).update(start_processing=int(time()))

        return [
            ScheduledTask(
                task_name="handle_tl_rpc_internal",
                schedule_id=str(scheduled.id),
                labels={},
                args=[],
                kwargs={
                    "call": CallRpcInternal(obj=DeleteScheduledMessage(message_id=scheduled.message_id)).write().hex(),
                },
                time=datetime.fromtimestamp(scheduled.scheduled_for, UTC),
            )
            for scheduled in scheduled_messages
        ]

    async def get_schedules(self) -> list[ScheduledTask]:
        await self._reset_scheduled_to_send_stuck_messages()

        return [
            *(await self._get_scheduled_to_send_messages()),
            *(await self._get_scheduled_to_delete_messages()),
        ]


class Scheduler:
    def __init__(self, rabbitmq_address: str | None = None, *, _broker: AsyncBroker | None = None) -> None:
        if AioPikaBroker is None or rabbitmq_address is None:
            logger.info("Scheduler is initializing with InMemoryBroker")
            self.broker = _broker or InMemoryBroker()
        else:
            logger.info("Scheduler is initializing with AioPikaBroker")
            self.broker = AioPikaBroker(rabbitmq_address)

        self.scheduler = TaskiqScheduler(self.broker, sources=[OrmDatabaseScheduleSource()])
