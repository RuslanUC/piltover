from asyncio import StreamWriter, StreamReader
from io import BytesIO

import pytest
import pytest_asyncio
from mtproto import ConnectionRole, Connection
from mtproto.packets import UnencryptedMessagePacket, BasePacket
from pyrogram.crypto import rsa
from pyrogram.crypto.rsa import PublicKey
from pyrogram.session import Auth
from pyrogram.connection import Connection as PyroConnection
from tortoise import Tortoise, connections

from piltover.app.__main__ import app
from piltover.server import Server
from piltover.tl import TLObject
from piltover.utils import get_public_key_fingerprint


@pytest_asyncio.fixture
async def app_server() -> Server:
    await Tortoise.init(
        db_url="sqlite://:memory:",
        modules={"models": ["piltover.db.models"]},
        _create_db=True,
    )

    yield app._server

    await connections.close_all()


class TestWriter(StreamWriter):
    def __init__(self, reader: StreamReader):
        self._reader = reader
        self._buffer = b""
        self._closed = False

    def write(self, data: bytes) -> None:
        if self._closed:
            return
        self._buffer += data

    def _drain(self) -> None:
        data, self._buffer = self._buffer, b""
        self._reader.feed_data(data)
        self._reader.feed_data(b"")

    async def drain(self) -> None:
        if self._closed:
            return
        self._drain()

    def close(self) -> None:
        if self._closed:
            return
        self._drain()
        self._reader.feed_eof()
        self._closed = True

    async def wait_closed(self) -> None:
        ...

    def get_extra_info(self, name, default=None):
        if name == "peername":
            return "127.0.0.1", 0
        return default


def create_rw_pair() -> tuple[StreamReader, StreamWriter, StreamReader, StreamWriter]:
    this_reader = StreamReader()
    other_reader = StreamReader()
    this_writer = TestWriter(other_reader)
    other_writer = TestWriter(this_reader)
    return this_reader, this_writer, other_reader, other_writer


async def read_until_packet(reader: StreamReader, conn: Connection) -> BasePacket:
    data = b""
    while True:
        if (packet := conn.receive(data)) is not None:
            return packet
        data = await reader.read(1024)


class Auth_(Auth):
    MAX_RETRIES = 0

    def __init__(self, reader: StreamReader, writer: StreamWriter, conn: Connection):
        self.dc_id = 2
        self.test_mode = False
        self.ipv6 = None
        self.proxy = None

        self.connection = None

        self._connection = conn
        self.reader = reader
        self.writer = writer

    async def _empty(self, *args, **kwargs) -> None:
        ...

    async def invoke(self, data):
        self.writer.write(self._connection.send(UnencryptedMessagePacket(
            message_id=0,
            message_data=data.write()
        )))
        await self.writer.drain()
        resp = await read_until_packet(self.reader, self._connection)
        assert isinstance(resp, UnencryptedMessagePacket)
        assert TLObject.read(BytesIO(resp.message_data)) is not None

        return self.unpack(BytesIO(b"\x00" * 20 + resp.message_data))

    async def create(self):
        orig_connect = getattr(PyroConnection, "connect")
        orig_close = getattr(PyroConnection, "close")
        setattr(PyroConnection, "connect", self.__class__._empty)
        setattr(PyroConnection, "close", self.__class__._empty)
        try:
            return await super().create()
        finally:
            setattr(PyroConnection, "connect", orig_connect)
            setattr(PyroConnection, "close", orig_close)


@pytest.mark.asyncio
async def test_key_generation(app_server: Server) -> None:
    fingerprint = get_public_key_fingerprint(app_server.server_keys.public_key, signed=True)
    public_key = app_server.public_key.public_numbers()
    rsa.server_public_keys[fingerprint] = PublicKey(public_key.n, public_key.e)

    conn = Connection(ConnectionRole.CLIENT)
    reader, writer, *server_rw = create_rw_pair()
    await app_server.accept_client(*server_rw)

    auth_key = await Auth_(reader, writer, conn).create()
    assert auth_key is not None
