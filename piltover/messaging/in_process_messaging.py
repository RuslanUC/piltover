from __future__ import annotations

import asyncio
import random
from collections.abc import Callable, Awaitable
from uuid import uuid4

try:
    from typing import override
except ImportError:
    from typing_extensions import override

from .base import BaseSubscription, BaseMessage, BaseMessaging
from ..exceptions import Unreachable


class InProcessSubscription(BaseSubscription):
    __slots__ = ("subject", "_callback", "queue", "_messaging", "_waiter",)

    def __init__(
            self,
            subject: str,
            callback: Callable[[BaseMessage], Awaitable[None]] | None,
            queue: str,
            messaging: InProcessMessaging
    ) -> None:
        self.subject = subject
        self._callback = callback
        self.queue = queue
        self._messaging = messaging
        self._waiter: asyncio.Future[BaseMessage] | None = None

    @override
    async def unsubscribe(self, wait_for_pending: bool = False) -> None:
        self._messaging.unsubscribe(self)

    @override
    async def receive(self, timeout: float) -> BaseMessage:
        if self._waiter is not None:
            raise Unreachable

        self._waiter = waiter = asyncio.get_running_loop().create_future()

        try:
            return await asyncio.wait_for(waiter, timeout)
        finally:
            self._waiter = None

    async def new_message(self, message: InProcessMessage) -> None:
        if self._waiter is not None:
            self._waiter.set_result(message)
            self._waiter = None
        if self._callback is not None:
            await self._callback(message)


class InProcessMessage(BaseMessage):
    __slots__ = ("_msg", "_messaging", "_reply",)

    def __init__(self, data: bytes, messaging: InProcessMessaging, reply: str = "") -> None:
        super().__init__(data)
        self._messaging = messaging
        self._reply = reply

    @override
    async def respond(self, payload: bytes) -> None:
        if self._reply:
            await self._messaging.publish(self._reply, payload)


class InProcessMessaging(BaseMessaging):
    __slots__ = ("_subscriptions_by_subject", "_lock", "_tasks")

    def __init__(self) -> None:
        self._subscriptions_by_subject: dict[str, dict[str, set[InProcessSubscription]]] = {}
        self._tasks: set[asyncio.Task] = set()

    @override
    async def start(self) -> None:
        ...

    @override
    async def stop(self) -> None:
        self._subscriptions_by_subject.clear()

    @override
    async def publish(self, subject: str, payload: bytes, reply: str = "") -> None:
        if subject not in self._subscriptions_by_subject:
            return

        message = InProcessMessage(payload, self, reply)

        loop = asyncio.get_running_loop()
        for queue, subs in self._subscriptions_by_subject[subject].items():
            if not queue:
                for sub in subs:
                    self._tasks.add(task := loop.create_task(sub.new_message(message)))
                    task.add_done_callback(self._tasks.discard)
            else:
                sub = random.choice(list(subs))
                self._tasks.add(task := loop.create_task(sub.new_message(message)))
                task.add_done_callback(self._tasks.discard)

    @override
    async def request(self, subject: str, payload: bytes, timeout: float) -> BaseMessage:
        reply_subject = f"_REPLY.{uuid4()}"
        reply_sub = await self.subscribe(reply_subject)
        await self.publish(subject, payload, reply_subject)
        try:
            return await reply_sub.receive(timeout)
        finally:
            await reply_sub.unsubscribe()

    @override
    async def subscribe(
            self,
            subject: str,
            callback: Callable[[BaseMessage], Awaitable[None]] | None = None,
            queue: str = "",
            **backend_args,
    ) -> BaseSubscription:
        sub = InProcessSubscription(subject, callback, queue, self)

        if subject not in self._subscriptions_by_subject:
            self._subscriptions_by_subject[subject] = {}
        if queue not in self._subscriptions_by_subject[subject]:
            self._subscriptions_by_subject[subject][queue] = set()

        self._subscriptions_by_subject[subject][queue].add(sub)
        return sub

    def unsubscribe(self, sub: InProcessSubscription) -> None:
        if sub.subject not in self._subscriptions_by_subject:
            return
        if sub.queue not in self._subscriptions_by_subject[sub.subject]:
            return

        self._subscriptions_by_subject[sub.subject][sub.queue].discard(sub)

        if not self._subscriptions_by_subject[sub.subject][sub.queue]:
            del self._subscriptions_by_subject[sub.subject][sub.queue]
        if not self._subscriptions_by_subject[sub.subject]:
            del self._subscriptions_by_subject[sub.subject]
