from __future__ import annotations

import asyncio

from loguru import logger
from taskiq import TaskiqScheduler


async def run_scheduler_loop_every_100ms(scheduler: TaskiqScheduler) -> None:
    from taskiq.cli.scheduler.run import get_all_schedules, get_task_delay, delayed_send, logger as taskiq_logger

    logger.debug("Starting taskiq scheduler")

    loop = asyncio.get_event_loop()
    while True:
        scheduled_tasks = await get_all_schedules(scheduler)
        logger.trace(f"Got {len(scheduled_tasks)} scheduled tasks")
        for source, task_list in scheduled_tasks.items():
            for task in task_list:
                try:
                    task_delay = get_task_delay(task)
                except ValueError:
                    taskiq_logger.warning(
                        "Cannot parse cron: %s for task: %s, schedule_id: %s",
                        task.cron,
                        task.task_name,
                        task.schedule_id,
                    )
                    continue
                logger.trace(f"Task delay is {task_delay} seconds")
                if task_delay is not None:
                    loop.create_task(delayed_send(scheduler, source, task, task_delay))
        await asyncio.sleep(.25)
