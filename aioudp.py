from __future__ import annotations

import asyncio
import warnings
from typing import Callable, TypeVar

__all__ = ["open_local_endpoint", "open_remote_endpoint"]
T = TypeVar("T")
Addr = tuple[str, int]


class DatagramEndpointProtocol(asyncio.DatagramProtocol):
    def __init__(self, endpoint: Endpoint) -> None:
        self._endpoint = endpoint

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:
        self._endpoint._transport = transport

    def connection_lost(self, exc: Exception) -> None:
        assert exc is None
        if self._endpoint._write_ready_future is not None:
            self._endpoint._write_ready_future.set_result(None)
        self._endpoint.close()

    def datagram_received(self, data: bytes, addr: Addr) -> None:
        self._endpoint.feed_datagram(data, addr)

    def error_received(self, exc: Exception) -> None:
        warnings.warn(f"Endpoint received an error: {exc!r}")

    def pause_writing(self) -> None:
        assert self._endpoint._write_ready_future is None
        loop = self._endpoint._transport._loop
        self._endpoint._write_ready_future = loop.create_future()

    def resume_writing(self) -> None:
        assert self._endpoint._write_ready_future is not None
        self._endpoint._write_ready_future.set_result(None)
        self._endpoint._write_ready_future = None


class Endpoint:
    def __init__(self, queue_size: int | None = None) -> None:
        self._queue = asyncio.Queue(queue_size or 0)
        self._closed = False
        self._transport = None
        self._write_ready_future = None

    def feed_datagram(self, data: bytes | None, addr: Addr | None) -> None:
        try:
            self._queue.put_nowait((data, addr))
        except asyncio.QueueFull:
            warnings.warn("Endpoint queue is full")

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._queue.empty():
            self.feed_datagram(None, None)
        if self._transport:
            self._transport.close()

    def send(self, data: bytes, addr: Addr | None) -> None:
        if self._closed:
            raise IOError("Endpoint is closed")
        self._transport.sendto(data, addr)

    async def receive(self) -> tuple[bytes, Addr]:
        if self._queue.empty() and self._closed:
            raise IOError("Endpoint is closed")
        data, addr = await self._queue.get()
        if data is None:
            raise IOError("Endpoint is closed")
        return data, addr

    def abort(self) -> None:
        if self._closed:
            raise IOError("Endpoint is closed")
        self._transport.abort()
        self.close()

    async def drain(self) -> None:
        if self._write_ready_future is not None:
            await self._write_ready_future

    @property
    def address(self) -> Addr:
        return self._transport.get_extra_info("socket").getsockname()

    @property
    def closed(self) -> bool:
        return self._closed


class LocalEndpoint(Endpoint):
    pass


class RemoteEndpoint(Endpoint):
    def send(self, data: bytes) -> None:
        super().send(data, None)

    async def receive(self) -> bytes:
        data, addr = await super().receive()
        return data


async def open_datagram_endpoint(
        host: str, port: int, *, endpoint_factory: Callable[[], T] = Endpoint, remote: bool = False, **kwargs,
) -> T:
    """
    Open and return a datagram endpoint.
    The default endpoint factory is the Endpoint class.
    The endpoint can be made local or remote using the remote argument.
    Extra keyword arguments are forwarded to `loop.create_datagram_endpoint`.
    """

    loop = asyncio.get_event_loop()
    endpoint = endpoint_factory()
    kwargs["remote_addr" if remote else "local_addr"] = host, port
    kwargs["protocol_factory"] = lambda: DatagramEndpointProtocol(endpoint)
    await loop.create_datagram_endpoint(**kwargs)
    return endpoint


async def open_local_endpoint(
        host: str = "0.0.0.0", port: int = 0, *, queue_size: int | None = None, **kwargs,
) -> LocalEndpoint:
    """
    Open and return a local datagram endpoint.
    An optional queue size arguement can be provided.
    Extra keyword arguments are forwarded to `loop.create_datagram_endpoint`.
    """

    return await open_datagram_endpoint(
        host, port, remote=False, endpoint_factory=lambda: LocalEndpoint(queue_size), **kwargs,
    )


async def open_remote_endpoint(host: str, port: int, *, queue_size: int | None = None, **kwargs) -> RemoteEndpoint:
    """
    Open and return a remote datagram endpoint.
    An optional queue size arguement can be provided.
    Extra keyword arguments are forwarded to `loop.create_datagram_endpoint`.
    """

    return await open_datagram_endpoint(
        host, port, remote=True, endpoint_factory=lambda: RemoteEndpoint(queue_size), **kwargs
    )
