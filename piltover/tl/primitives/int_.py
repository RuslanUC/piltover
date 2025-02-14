from __future__ import annotations

from io import BytesIO

from piltover.utils.utils import classinstancemethod


class Int(int):
    BIT_SIZE = 32
    SIZE = BIT_SIZE // 8

    @classmethod
    def read_bytes(cls, data: bytes, signed: bool = True) -> int:
        return int.from_bytes(data, "little", signed=signed)

    @classmethod
    def read(cls, stream: BytesIO, signed: bool = True) -> int:
        return cls.read_bytes(stream.read(cls.SIZE), signed)

    # noinspection PyMethodParameters
    @classinstancemethod
    def write(cls: type[Int], self: int, signed: bool = True) -> bytes:
        return self.to_bytes(cls.SIZE, "little", signed=signed)


class Long(Int):
    BIT_SIZE = 64
    SIZE = BIT_SIZE // 8


class Int128(Int):
    BIT_SIZE = 128
    SIZE = BIT_SIZE // 8


class Int256(Int):
    BIT_SIZE = 256
    SIZE = BIT_SIZE // 8
