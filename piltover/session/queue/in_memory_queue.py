import asyncio
from collections.abc import MutableMapping
from queue import SimpleQueue
from threading import Thread
from typing import TypeVar, Iterable, Generic

from loguru import logger
from sortedcontainers import SortedSet

from piltover.session.queue.base_queue import BaseMessageQueue, MessagePullResult, QueueKey

T = TypeVar("T")
TKey = TypeVar("TKey")
TVal = TypeVar("TVal")


class MaxLenSortedCollection(MutableMapping[TKey, TVal]):
    __slots__ = ("_set", "_dict", "_max_size")

    def __init__(self, max_size: int) -> None:
        self._set = SortedSet()
        self._dict: dict[TKey, TVal] = {}
        self._max_size = max_size

    def __len__(self) -> int:
        return len(self._dict)

    def __iter__(self):
        raise NotImplementedError

    def __contains__(self, x: TKey, /) -> bool:
        return x in self._dict

    def __setitem__(self, key: TKey, value: TVal, /) -> None:
        assert key not in self._dict
        while len(self) >= self._max_size:
            del self._dict[self._set.pop(0)]
        self._dict[key] = value
        self._set.add(key)

    def __delitem__(self, key: TKey, /) -> None:
        if key not in self._dict:
            raise KeyError(key)
        del self._dict[key]
        self._set.remove(key)

    def __getitem__(self, key: TKey, /) -> TVal:
        if key not in self._dict:
            raise KeyError(key)
        return self._dict[key]

    def delete_before(self, key: TKey) -> None:
        while self._set and (to_remove := self._set[0]) < key:
            del self[to_remove]

    def get_next(self, key: TKey) -> tuple[TKey, TVal] | None:
        idx = self._set.bisect_right(key)
        if idx >= len(self._set):
            return None
        next_key = self._set[idx]
        return next_key, self._dict[next_key]

    def remove_many(self, keys: Iterable[TKey]) -> None:
        for key in keys:
            if key not in self._dict:
                continue
            self._set.remove(key)
            del self._dict[key]


class WorkerJob(Generic[T]):
    __slots__ = ("future",)

    def __init__(self, future: asyncio.Future[T]) -> None:
        self.future = future


class WorkerStopJob(WorkerJob[None]):
    __slots__ = ()


class QueuePushJob(WorkerJob[None]):
    __slots__ = ("session_key", "message_id", "seq_no", "data",)

    def __init__(
            self, future: asyncio.Future[T], session_key: QueueKey, message_id: int, seq_no: int, data: bytes,
    ) -> None:
        super().__init__(future)
        self.session_key = session_key
        self.message_id = message_id
        self.seq_no = seq_no
        self.data = data


class QueuePullJob(WorkerJob[list[MessagePullResult]]):
    __slots__ = ("sessions",)

    def __init__(self, future: asyncio.Future[T], sessions: dict[QueueKey, int]) -> None:
        super().__init__(future)
        self.sessions = sessions


class QueueUnsubSessionsJob(WorkerJob[None]):
    __slots__ = ("sessions",)

    def __init__(self, future: asyncio.Future[T], sessions: list[QueueKey]) -> None:
        super().__init__(future)
        self.sessions = sessions


class QueueAckJob(WorkerJob[None]):
    __slots__ = ("session_key", "message_ids",)

    def __init__(self, future: asyncio.Future[T], session_key: QueueKey, message_ids: list[int]) -> None:
        super().__init__(future)
        self.session_key = session_key
        self.message_ids = message_ids


# TODO: rename to InMemoryMessageStorage
class InMemoryMessageQueue(BaseMessageQueue):
    def __init__(self) -> None:
        self.by_session_key: dict[QueueKey, MaxLenSortedCollection[int, tuple[int, bytes]]] = {}
        self.waiters: dict[QueueKey, tuple[asyncio.Future[list[MessagePullResult]], list[QueueKey]]] = {}
        self.queue: SimpleQueue[WorkerJob] = SimpleQueue()
        self.loop: asyncio.AbstractEventLoop | None = None
        self.thread: Thread | None = None

    # TODO: run background task to remove old messages and sessions

    async def start(self) -> None:
        if self.loop is not None:
            return
        self.loop = asyncio.get_running_loop()
        self.thread = thread = Thread(target=self._worker_thread)
        thread.start()
        logger.info("Started InMemoryMessageQueue")

    async def stop(self) -> None:
        self.queue.put(job := WorkerStopJob(self.loop.create_future()), False)
        await job.future
        self.loop = self.thread = None

    def _notify(self, session_key: QueueKey, message_id: int, seq_no: int, data: bytes) -> None:
        if session_key not in self.waiters:
            return
        waiter, other_sessions = self.waiters[session_key]
        for other_key in other_sessions:
            del self.waiters[other_key]
        if self.loop is None:
            raise RuntimeError("_notify called after shutdown")
        self.loop.call_soon_threadsafe(waiter.set_result, [MessagePullResult(session_key, message_id, seq_no, data)])

    def _push_sync(self, session_key: QueueKey, message_id: int, seq_no: int, data: bytes) -> None:
        if session_key not in self.by_session_key:
            self.by_session_key[session_key] = MaxLenSortedCollection(256)
        self.by_session_key[session_key][message_id] = seq_no, data
        self._notify(session_key, message_id, seq_no, data)

    def _pull_sync(self, future: asyncio.Future[list[MessagePullResult]], sessions: dict[QueueKey, int]) -> None:
        result = []
        for session_key, message_id in sessions.items():
            if session_key in self.by_session_key \
                    and (data := self.by_session_key[session_key].get_next(message_id)) is not None:
                next_message_id, (next_seq_no, next_data) = data
                result.append(MessagePullResult(
                    session_key=session_key,
                    message_id=next_message_id,
                    seq_no=next_seq_no,
                    data=next_data,
                ))

        if result:
            if self.loop is None:
                raise RuntimeError("_pull_sync called after shutdown")
            self.loop.call_soon_threadsafe(future.set_result, result)
            return

        future_sessions = []

        for session_key, _ in sessions.items():
            if session_key in self.waiters:
                raise RuntimeError(f"Session key {session_key} is already in waiters list")
            self.waiters[session_key] = future, future_sessions
            future_sessions.append(session_key)

    def _unsub_sync(self, sessions: list[QueueKey]) -> None:
        for session_key in sessions:
            if session_key in self.waiters:
                del self.waiters[session_key]

    def _ack_sync(self, session_key: QueueKey, message_ids: list[int]) -> None:
        if session_key not in self.by_session_key:
            return
        self.by_session_key[session_key].remove_many(message_ids)

    def _worker_thread(self) -> None:
        while True:
            job = self.queue.get()
            if self.loop is None:
                raise RuntimeError("Got worker job after shutdown")

            future = job.future
            if isinstance(job, WorkerStopJob):
                self.loop.call_soon_threadsafe(future.set_result, None)
                return
            elif isinstance(job, QueuePushJob):
                self._push_sync(job.session_key, job.message_id, job.seq_no, job.data)
                self.loop.call_soon_threadsafe(future.set_result, None)
            elif isinstance(job, QueuePullJob):
                self._pull_sync(future, job.sessions)
            elif isinstance(job, QueuePullJob):
                self._pull_sync(future, job.sessions)
            elif isinstance(job, QueueUnsubSessionsJob):
                self._unsub_sync(job.sessions)
                self.loop.call_soon_threadsafe(future.set_result, None)
            elif isinstance(job, QueueAckJob):
                self._ack_sync(job.session_key, job.message_ids)
                self.loop.call_soon_threadsafe(future.set_result, None)
            else:
                raise RuntimeError(f"Unknown worker job class: {job}")

    async def push(self, session_key: QueueKey, message_id: int, seq_no: int, data: bytes) -> None:
        self.queue.put(job := QueuePushJob(self.loop.create_future(), session_key, message_id, seq_no, data), False)
        await job.future

    async def pull(self, sessions: dict[QueueKey, int], timeout: float = 0.1) -> list[MessagePullResult]:
        self.queue.put(job := QueuePullJob(self.loop.create_future(), sessions), False)
        try:
            result = await asyncio.wait_for(job.future, timeout=timeout)
        except TimeoutError:
            ...
        else:
            return result

        sessions_keys = list(sessions.keys())
        self.queue.put(job := QueueUnsubSessionsJob(self.loop.create_future(), sessions_keys), False)
        await job.future

        return []

    async def ack(self, session_key: QueueKey, message_ids: list[int]) -> None:
        self.queue.put(job := QueueAckJob(self.loop.create_future(), session_key, message_ids), False)
        await job.future
