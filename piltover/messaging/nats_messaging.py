from __future__ import annotations

import functools
from collections.abc import Callable, Awaitable

try:
    from typing import override
except ImportError:
    from typing_extensions import override

from nats import NATS
from nats.aio.msg import Msg
from nats.aio.subscription import Subscription

from .base import BaseSubscription, BaseMessage, BaseMessaging


class NatsSubscription(BaseSubscription):
    __slots__ = ("_sub",)

    def __init__(self, sub: Subscription) -> None:
        self._sub = sub

    @override
    async def unsubscribe(self, wait_for_pending: bool = False) -> None:
        if wait_for_pending:
            await self._sub.drain()
        else:
            await self._sub.unsubscribe()

    @override
    async def receive(self, timeout: float) -> BaseMessage:
        msg = await self._sub.next_msg(timeout)
        return NatsMessage(msg)


class NatsMessage(BaseMessage):
    __slots__ = ("_msg",)

    def __init__(self, msg: Msg) -> None:
        super().__init__(msg.data)
        self._msg = msg

    @override
    async def respond(self, payload: bytes) -> None:
        if self._msg.reply:
            await self._msg.respond(payload)


class NatsMessaging(BaseMessaging):
    __slots__ = ("_client", "_address",)

    def __init__(self, address: str) -> None:
        self._client = NATS()
        self._address = address

    @override
    async def start(self) -> None:
        await self._client.connect(self._address)

    @override
    async def stop(self) -> None:
        await self._client.drain()

    @override
    async def publish(self, subject: str, payload: bytes) -> None:
        await self._client.publish(subject, payload)

    @override
    async def request(self, subject: str, payload: bytes, timeout: float) -> BaseMessage:
        msg = await self._client.request(subject, payload, timeout)
        return NatsMessage(msg)

    @override
    async def subscribe(
            self,
            subject: str,
            callback: Callable[[BaseMessage], Awaitable[None]] | None = None,
            queue: str = "",
            **backend_args,
    ) -> BaseSubscription:
        if callback is None:
            _callback = None
        else:
            @functools.wraps(callback)
            async def _callback(msg: Msg) -> None:
                await callback(NatsMessage(msg))

        sub = await self._client.subscribe(subject, queue, _callback, **backend_args)
        return NatsSubscription(sub)
