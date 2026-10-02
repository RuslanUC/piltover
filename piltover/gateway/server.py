from __future__ import annotations

import asyncio
from pathlib import Path

from loguru import logger

from piltover.gateway.client import Client
from piltover.messaging import BaseMessaging
from piltover.utils import get_public_key_fingerprint, load_private_key, load_public_key, Keys


class Gateway:
    HOST = "0.0.0.0"
    PORT = 4430

    def __init__(self, data_dir: Path, server_keys: Keys, salt_key: bytes, messaging: BaseMessaging) -> None:
        self.data_dir = data_dir

        self.server_keys = server_keys
        self.salt_key = salt_key

        self.public_key = load_public_key(self.server_keys.public_key)
        self.private_key = load_private_key(self.server_keys.private_key)

        self.fingerprint: int = get_public_key_fingerprint(self.server_keys.public_key)
        self.fingerprint_signed: int = get_public_key_fingerprint(self.server_keys.public_key, True)

        self.messaging = messaging

    @logger.catch
    async def accept_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        client = Client(self, reader, writer)
        await client.worker()
