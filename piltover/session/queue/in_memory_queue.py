import asyncio
from collections.abc import MutableMapping
from typing import TypeVar, Iterable

from sortedcontainers import SortedSet

from piltover.session.queue.base_queue import BaseMessageQueue, MessagePullResult, QueueKey

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
        idx = self._set.bisect_key_right(key)
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


# TODO: rename to InMemoryMessageStorage
class InMemoryMessageQueue(BaseMessageQueue):
    def __init__(self) -> None:
        self.by_session_key: dict[QueueKey, MaxLenSortedCollection[int, bytes]] = {}
        self.waiters: dict[QueueKey, asyncio.Future] = {}

    # TODO: run background task to remove old messages and sessions

    async def push(self, session_key: QueueKey, message_id: int, data: bytes) -> None:
        if session_key not in self.by_session_key:
            self.by_session_key[session_key] = MaxLenSortedCollection(256)
        self.by_session_key[session_key][message_id] = data
        if (waiter := self.waiters.pop(session_key, None)) is not None:
            waiter.set_result(session_key)

    async def pull(self, sessions: dict[QueueKey, int], timeout: float = 0.1) -> list[MessagePullResult]:
        loop = asyncio.get_running_loop()

        result = []
        waiters: list[asyncio.Future[QueueKey]] = []
        waiters_to_cleanup: list[QueueKey] = []

        for session_key, message_id in sessions.items():
            await asyncio.sleep(0)
            if session_key in self.by_session_key \
                    and (data := self.by_session_key[session_key].get_next(message_id)) is not None:
                next_message_id, next_data = data
                result.append(MessagePullResult(
                    session_key=session_key,
                    message_id=next_message_id,
                    data=next_data,
                ))
                continue

            if session_key not in self.waiters:
                self.waiters[session_key] = waiter = loop.create_future()
                waiters.append(waiter)
                waiters_to_cleanup.append(session_key)

        if not waiters or result:
            for session_key in waiters_to_cleanup:
                del self.waiters[session_key]
            return result

        done, _ = await asyncio.wait(waiters, timeout=timeout, return_when=asyncio.FIRST_COMPLETED)
        for fut in done:
            session_with_data = await fut
            message_id = sessions[session_with_data]
            if session_with_data in self.by_session_key \
                    and (data := self.by_session_key[session_with_data].get_next(message_id)) is not None:
                next_message_id, next_data = data
                result.append(MessagePullResult(
                    session_key=session_with_data,
                    message_id=next_message_id,
                    data=next_data,
                ))

        for session_key in waiters_to_cleanup:
            del self.waiters[session_key]

        return result

    async def ack(self, session_key: QueueKey, message_ids: list[int]) -> None:
        if session_key not in self.by_session_key:
            return
        self.by_session_key[session_key].remove_many(message_ids)
