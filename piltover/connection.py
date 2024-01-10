import os
from abc import ABC, abstractmethod
from zlib import crc32

import tgcrypto

from piltover.enums import Transport
from piltover.utils.buffered_stream import BufferedStream, ObfuscatedStream


class Connection(ABC):
    stream: BufferedStream

    @staticmethod
    def new(transport: Transport, stream: BufferedStream) -> "Connection":
        MODES = {
            Transport.Abridged: TCPAbridged,
            Transport.Intermediate: TCPIntermediate,
            Transport.PaddedIntermediate: TCPIntermediatePadded,
            Transport.Full: TCPFull,
            Transport.Obfuscated: TCPObfuscated,
        }

        trans = MODES.get(transport, MODES[Transport.Intermediate])

        return trans(stream=stream)

    async def init(self) -> "Connection":
        return self

    @abstractmethod
    def __init__(self, stream: BufferedStream):
        ...

    @abstractmethod
    async def send(self, data: bytes):
        ...

    @abstractmethod
    async def recv(self) -> bytes:
        ...

    @abstractmethod
    async def close(self):
        ...


class TCPAbridged(Connection):
    def __init__(self, stream: BufferedStream):
        self.stream = stream

    async def send(self, data: bytes):
        # Round up length
        length = (len(data) + 3) // 4

        if length >= 0x7F:  # 127
            self.stream.write(b"\x7f")
            self.stream.write(length.to_bytes(3, byteorder="little"))
        else:
            self.stream.write(length.to_bytes(1, byteorder="little"))

        self.stream.write(data)
        await self.stream.drain()

    async def recv(self) -> bytes:
        length = await self.stream.read(1)
        #needQuickAck = (length[0] >> 7) == 1

        if length[0] & 0x7F == 0x7F:
            length = await self.stream.read(3)

        length = int.from_bytes(length, "little") * 4
        return await self.stream.read(length)

    async def close(self):
        await self.stream.close()


class TCPIntermediate(Connection):
    def __init__(self, stream: BufferedStream):
        self.stream = stream

    async def send(self, data: bytes):
        length = len(data)
        self.stream.write(length.to_bytes(4, "little", signed=False))
        self.stream.write(data)
        await self.stream.drain()

    async def recv(self) -> bytes:
        length = int.from_bytes(await self.stream.read(4), byteorder="little", signed=False)

        assert length != 0, "Received null length"
        # TODO: length check, allow for maximum buffer size (e.g. 1MB)
        # raise TooMuch

        payload = await self.stream.read(length)
        return payload

    async def close(self):
        await self.stream.close()


class TCPIntermediatePadded(TCPIntermediate):
    def __init__(self, stream: BufferedStream):
        super().__init__(stream)

    async def send(self, data: bytes):
        length = len(data)
        self.stream.write(length.to_bytes(4, "little", signed=False))
        self.stream.write(data + os.urandom(-len(data) % 16))
        await self.stream.drain()


class TCPFull(Connection):
    def __init__(self, stream: BufferedStream):
        self.stream = stream
        self.seq_no = 0
        self.client_seq_no = 0

    async def send(self, data: bytes):
        # length(4) + seq_no(4) + data(length) + crc32(4)
        length = (4 + 4 + len(data) + 4).to_bytes(4, "little", signed=False)
        self.seq_no += 1

        payload = length + self.seq_no.to_bytes(4, "little", signed=False) + data

        crc = crc32(payload)
        payload += crc.to_bytes(4, "little", signed=False)

        self.stream.write(payload)
        await self.stream.drain()

    async def recv(self) -> bytes:
        length = int.from_bytes(length_bytes := await self.stream.read(4), "little", signed=False)
        seq_no = int.from_bytes(seq_no_bytes := await self.stream.read(4), "little", signed=False)
        payload = await self.stream.read(length - 4 - 4 - 4)
        crc = int.from_bytes(await self.stream.read(4), "little", signed=False)

        assert crc == crc32(length_bytes + seq_no_bytes + payload), "Mismatching CRC32 in TCPFull.recv()"

        assert seq_no == self.client_seq_no, "Wrong seq_no"
        self.client_seq_no += 1

        return payload

    async def close(self):
        await self.stream.close()


class TCPObfuscated(Connection):
    def __init__(self, stream: BufferedStream):
        self.stream = stream
        self.conn: Connection | None = None

    async def init(self) -> Connection:
        nonce = await self.stream.read(64)
        temp = nonce[8:56][::-1]
        encrypt = (nonce[8:40], nonce[40:56], bytearray(1))
        decrypt = (temp[0:32], temp[32:48], bytearray(1))
        decrypted = tgcrypto.ctr256_decrypt(nonce, *encrypt)

        header = decrypted[56:56 + 4]

        obf_stream = ObfuscatedStream.from_stream(self.stream, encrypt, decrypt)
        if header == b"\xef\xef\xef\xef":
            return TCPAbridgedObfuscated(obf_stream)
        elif header == b"\xee\xee\xee\xee":
            return TCPIntermediateObfuscated(obf_stream)
        elif header == b"\xdd\xdd\xdd\xdd":
            return TCPPaddedIntermediateObfuscated(obf_stream)
        else:
            assert False, "idk, tcpfull maybe? or corrupted connection"

    async def send(self, data: bytes):
        ...

    async def recv(self) -> bytes:
        ...

    async def close(self):
        ...


class TCPAbridgedObfuscated(TCPAbridged):
    def __init__(self, stream: ObfuscatedStream):
        super().__init__(stream)


class TCPIntermediateObfuscated(TCPIntermediate):
    def __init__(self, stream: ObfuscatedStream):
        super().__init__(stream)


class TCPPaddedIntermediateObfuscated(TCPIntermediatePadded):
    def __init__(self, stream: ObfuscatedStream):
        super().__init__(stream)
