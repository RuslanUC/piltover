from __future__ import annotations

from io import BytesIO


class Bytes(bytes):
    @classmethod
    def read(cls, stream: BytesIO) -> bytes:
        count = stream.read(1)[0]
        padding = 1
        if count >= 254:
            count = int.from_bytes(stream.read(3), "little")
            padding = 4

        result = stream.read(count)
        padding += len(result)
        padding %= 4
        if padding:
            stream.read(4 - padding)

        return result

    @classmethod
    def write(cls, value: bytes) -> bytes:
        result = b""
        ln = len(value)
        if ln >= 0xFE:
            result += bytes([254])
            result += int.to_bytes(ln, 3, "little")
        else:
            result += bytes([ln])

        result += value
        padding = len(result) % 4
        if padding:
            result += b"\x00" * (4 - padding)

        return result


class String(str):
    @classmethod
    def read(cls, stream: BytesIO) -> str:
        return Bytes.read(stream).decode("utf8")

    @classmethod
    def write(cls, value: str) -> bytes:
        return Bytes.write(value.encode("utf8"))
