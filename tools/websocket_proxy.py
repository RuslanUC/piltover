import asyncio
import os
import signal

import websockets
from loguru import logger
from websockets import ConnectionClosedOK
from websockets.server import WebSocketServerProtocol, serve
from websockets.typing import Subprotocol


async def proxy(websocket: WebSocketServerProtocol):
    addr = websocket.remote_address[0]
    uuid = os.urandom(2).hex().upper()

    try:
        reader, writer = await asyncio.open_connection(host="localhost", port=4430)
        logger.info(f"{uuid} | Client connected: {addr}")

        async def remote_to_local():
            while True:
                data = await reader.read(1024 * 16)
                await websocket.send(data)

        async def local_to_remote():
            while True:
                data = await websocket.recv()
                assert isinstance(data, bytes), "Expected bytes"
                writer.write(data)
                await writer.drain()

        await asyncio.gather(remote_to_local(), local_to_remote())
    except ConnectionClosedOK:
        logger.warning(f"{uuid} | Client disconnected: {addr}")


async def main():
    loop = asyncio.get_running_loop()
    stop = loop.create_future()
    loop.add_signal_handler(signal.SIGTERM, stop.set_result, None)

    async with serve(
        proxy,
        "localhost",
        3000,
        subprotocols=[Subprotocol("binary")],
        select_subprotocol=lambda subprotocols, _: Subprotocol("binary"),
    ):
        logger.success("Server started")
        await stop


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.success("Server stopped")
