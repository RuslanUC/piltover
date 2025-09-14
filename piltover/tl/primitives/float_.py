from __future__ import annotations

from io import BytesIO
from struct import Struct

from piltover.utils.utils import classinstancemethod


class Float(float):
    STRUCT_FMT = Struct("<d")

    @classmethod
    def read(cls, stream: BytesIO) -> float:
        return cls.STRUCT_FMT.unpack(stream.read(8))[0]

    # noinspection PyMethodParameters
    @classinstancemethod
    def write(cls: type[Float], self: float) -> bytes:
        return cls.STRUCT_FMT.pack(self)
