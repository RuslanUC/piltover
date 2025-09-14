from __future__ import annotations

from io import BytesIO
from struct import Struct

from piltover.utils.utils import classinstancemethod


class Int(int):
    BIT_SIZE = 32
    SIZE = BIT_SIZE // 8
    STRUCT_FMT_I = Struct("<i")
    STRUCT_FMT_U = Struct("<I")

    @classmethod
    def read_bytes(cls, data: bytes, signed: bool = True) -> int:
        if signed:
            return cls.STRUCT_FMT_I.unpack(data)[0]
        return cls.STRUCT_FMT_U.unpack(data)[0]

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
    STRUCT_FMT_I = Struct("<q")
    STRUCT_FMT_U = Struct("<Q")


class BigInt(Int):
    BIT_SIZE = 0
    SIZE = 0
    STRUCT_FMT_I = STRUCT_FMT_U = None

    @classmethod
    def read_bytes(cls, data: bytes, signed: bool = True) -> int:
        return int.from_bytes(data[:cls.SIZE], "little", signed=signed)


class Int128(BigInt):
    BIT_SIZE = 128
    SIZE = BIT_SIZE // 8
    STRUCT_FMT_I = STRUCT_FMT_U = None


class Int256(BigInt):
    BIT_SIZE = 256
    SIZE = BIT_SIZE // 8
    STRUCT_FMT_I = STRUCT_FMT_U = None
