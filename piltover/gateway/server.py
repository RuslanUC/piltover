from __future__ import annotations

import asyncio
import base64
import os
from pathlib import Path
from typing import cast

import nats
from loguru import logger

from piltover.config import SYSTEM_CONFIG
from piltover.gateway.client import Client
from piltover.utils import gen_keys, get_public_key_fingerprint, load_private_key, load_public_key, Keys


class Gateway:
    HOST = "0.0.0.0"
    PORT = 4430

    def __init__(
            self, data_dir: Path, host: str = HOST, port: int = PORT, server_keys: Keys | None = None,
            salt_key: bytes | None = None,
    ):
        self.data_dir = data_dir

        self.host = host
        self.port = port

        self.server_keys = server_keys
        if self.server_keys is None:
            self.server_keys = gen_keys()

        self.public_key = load_public_key(self.server_keys.public_key)
        self.private_key = load_private_key(self.server_keys.private_key)

        self.fingerprint: int = get_public_key_fingerprint(self.server_keys.public_key)
        self.fingerprint_signed: int = get_public_key_fingerprint(self.server_keys.public_key, True)

        self.clients: dict[str, Client] = {}

        if salt_key is None:
            salt_key = os.urandom(32)
            logger.info(f"Salt key is None, generating new one: {base64.b64encode(salt_key).decode('latin1')}")

        self.salt_key = cast(bytes, salt_key)

        self.nc = nats.NATS()

    @logger.catch
    async def accept_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        client = Client(server=self, reader=reader, writer=writer)
        await client.worker()

    async def start(self) -> None:
        await self.nc.connect(SYSTEM_CONFIG.nats_address)

    async def serve(self):
        server = await asyncio.start_server(self.accept_client, self.host, self.port)
        async with server:
            await server.serve_forever()
