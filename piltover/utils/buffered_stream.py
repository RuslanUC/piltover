from __future__ import annotations

from asyncio import StreamReader, StreamWriter
from typing import Any

import tgcrypto
from loguru import logger

from piltover.exceptions import Disconnection


def check(data: bytes) -> bytes:
    if not data:
        # data = b""
        logger.error("Empty data received")
        raise Disconnection()
    return data


class BufferedStream:
    def __init__(self, reader: StreamReader, writer: StreamWriter):
        self.reader = reader
        self.writer = writer
        self.buf = b""

    async def read(self, n: int = ...) -> bytes:
        try:
            if n is ...:
                return check(await self.reader.read())

            cached = min(len(self.buf), n)
            data = self.buf[:cached]
            self.buf = self.buf[cached:]

            if len(data) < n:
                return data + check(await self.reader.read(n - cached))
            return data
        except ConnectionResetError:
            raise Disconnection()

    async def peek(self, n: int) -> bytes:
        cached = min(len(self.buf), n)
        data = self.buf[:cached]

        if len(data) < n:
            got = check(await self.reader.read(n - cached))
            self.buf += got
            return self.buf[:n]
        return data

    def write(self, data: bytes):
        self.writer.write(data)

    async def drain(self):
        await self.writer.drain()

    async def close(self):
        self.writer.close()
        await self.writer.wait_closed()

    def get_extra_info(self, name: str, default: Any = ...) -> Any:
        return self.writer.get_extra_info(name=name, default=default)


class ObfuscatedStream(BufferedStream):
    def __init__(self, reader: StreamReader, writer: StreamWriter, encrypt: tuple[bytes, bytes, bytearray],
                 decrypt: tuple[bytes, bytes, bytearray]):
        super().__init__(reader, writer)
        self.encrypt = encrypt
        self.decrypt = decrypt

    @classmethod
    def from_stream(cls, stream: BufferedStream, encrypt: tuple[bytes, bytes, bytearray],
                    decrypt: tuple[bytes, bytes, bytearray]) -> ObfuscatedStream:
        obf_stream = ObfuscatedStream(stream.reader, stream.writer, encrypt, decrypt)
        obf_stream.buf = stream.buf
        return obf_stream

    async def read(self, n: int = ...) -> bytes:
        data = await super().read(n)
        return tgcrypto.ctr256_decrypt(data, *self.encrypt)

    def write(self, data: bytes) -> None:
        data = tgcrypto.ctr256_encrypt(data, *self.decrypt)
        super().write(data)
