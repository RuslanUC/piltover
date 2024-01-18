from __future__ import annotations

import piltover.tl_new as tl_new
from piltover.utils.utils import classinstancemethod


class Int(int):
    BIT_SIZE = 32
    SIZE = BIT_SIZE // 8

    @classmethod
    def read(cls, stream) -> Int:
        return tl_new.SerializationUtils.read(stream, cls)

    @classinstancemethod
    def write(cls: type[int], self: int) -> bytes:
        return tl_new.SerializationUtils.write(self, cls)


class Long(Int):
    BIT_SIZE = 64
    SIZE = BIT_SIZE // 8


class Int128(Int):
    BIT_SIZE = 128
    SIZE = BIT_SIZE // 8


class Int256(Int):
    BIT_SIZE = 256
    SIZE = BIT_SIZE // 8
