import asyncio
from asyncio import Event

from taskiq import TaskiqResult
from taskiq.brokers.inmemory_broker import InmemoryResultBackend


class FasterInmemoryResultBackend(InmemoryResultBackend):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._events: dict[str, Event] = {}

    async def set_result(self, task_id: str, result: TaskiqResult) -> None:
        await super().set_result(task_id, result)
        if task_id in self._events:
            event = self._events.pop(task_id)
            event.set()

    async def is_result_ready(self, task_id: str) -> bool:
        """
        Not actually just checks if a result is ready, but waits for it for default timeout of 0.2 seconds.

        :param task_id: id of a task to check.
        :return: True if ready.
        """
        if task_id in self.results:
            return True

        if task_id not in self._events:
            # TODO: remove old Event objects from self._events?
            self._events[task_id] = Event()

        try:
            await asyncio.wait_for(self._events[task_id].wait(), 0.2)
            return True
        except TimeoutError:
            return False
