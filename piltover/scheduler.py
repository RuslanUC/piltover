from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime

from loguru import logger
from tortoise.expressions import Q, F
from tortoise.transactions import in_transaction

from piltover.db.enums import ScheduledTaskState, ScheduledTaskType
from piltover.db.models.scheduled_task import ScheduledTask
from piltover.exceptions import Unreachable
from piltover.messaging import BaseMessaging
from piltover.tl import TLObject
from piltover.tl.functions.internal import CallRpcInternal, SendScheduledMessage, ScheduledDeleteMessage

SUBJECT = "piltover.worker.rpc.internal"


class Scheduler:
    def __init__(
            self,
            messaging: BaseMessaging,
            loop_interval: float = 60,
            batch_size: int = 100,
            max_batches_per_loop: int = 10,
            max_failed_retries: int = 5,
    ) -> None:
        self.messaging = messaging
        self.loop_interval = loop_interval
        self.batch_size = batch_size
        self.max_batches_per_loop = max_batches_per_loop
        self.max_failed_retries = max_failed_retries

    async def run(self, stop: asyncio.Event | None = None) -> None:
        while stop is None or not stop.is_set():
            now = datetime.now(UTC)

            start_time = time.monotonic()

            for _ in range(self.max_batches_per_loop):
                async with in_transaction():
                    tasks = await ScheduledTask.select_for_update(skip_locked=True).filter(
                        Q(
                            Q(state=ScheduledTaskState.SCHEDULED, scheduled_at__lt=now),
                            Q(
                                Q(state__not=ScheduledTaskState.SCHEDULED),
                                next_attempt_at__lt=now,
                                generation__lt=self.max_failed_retries,
                            ),
                            join_type=Q.OR,
                        ),
                    ).order_by("id").limit(self.batch_size)

                    await ScheduledTask.filter(id__in=[task.id for task in tasks]).update(
                        state=ScheduledTaskState.DISPATCHING,
                        generation=F("generation") + 1,
                    )

                logger.debug("Got {tasks_num} scheduled tasks", tasks_num=len(tasks))

                for task in tasks:
                    task.generation += 1
                    if task.type is ScheduledTaskType.SEND_MESSAGE:
                        await self._call_internal(SendScheduledMessage(task_id=task.id, generation=task.generation))
                    elif task.type is ScheduledTaskType.DELETE_MESSAGE:
                        await self._call_internal(ScheduledDeleteMessage(task_id=task.id, generation=task.generation))
                    else:
                        raise Unreachable

                if len(tasks) != self.batch_size:
                    break

            end_time = time.monotonic()
            sleep_time = max(1, self.loop_interval - (end_time - start_time))

            if stop is None:
                await asyncio.sleep(sleep_time)
            else:
                try:
                    await asyncio.wait_for(stop.wait(), timeout=sleep_time)
                except TimeoutError:
                    ...

    async def _call_internal(self, request: TLObject) -> None:
        logger.info("Scheduler is sending {obj} to workers", obj=request)
        await self.messaging.publish("piltover.worker.rpc.internal", CallRpcInternal(obj=request).write())
