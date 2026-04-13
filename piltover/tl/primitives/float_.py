from __future__ import annotations

from io import BytesIO
from struct import Struct


class Float(float):
    STRUCT_FMT = Struct("<d")

    @classmethod
    def read(cls, stream: BytesIO) -> float:
        return cls.STRUCT_FMT.unpack(stream.read(8))[0]

    @classmethod
    def write(cls, value: float) -> bytes:
        return cls.STRUCT_FMT.pack(value)
