from __future__ import annotations

from piltover.utils.utils import classinstancemethod


class Int(int):
    BIT_SIZE = 32
    SIZE = BIT_SIZE // 8

    @classmethod
    def read(cls, stream) -> int:
        return int.from_bytes(stream.read(cls.SIZE), "little")

    # noinspection PyMethodParameters
    @classinstancemethod
    def write(cls: type[Int], self: int) -> bytes:
        return self.to_bytes(cls.SIZE, 'little')


class Long(Int):
    BIT_SIZE = 64
    SIZE = BIT_SIZE // 8


class Int128(Int):
    BIT_SIZE = 128
    SIZE = BIT_SIZE // 8


class Int256(Int):
    BIT_SIZE = 256
    SIZE = BIT_SIZE // 8
