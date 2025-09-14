from __future__ import annotations

from abc import ABC
from io import BytesIO

from piltover.exceptions import InvalidConstructorException
from piltover.tl import primitives


class Bool(ABC):
    @classmethod
    def read(cls, stream: BytesIO) -> bool:
        bool_constructor = stream.read(4)
        if bool_constructor not in (primitives.BOOL_TRUE, primitives.BOOL_FALSE):
            raise InvalidConstructorException(bool_constructor, False, stream.read())

        return bool_constructor == primitives.BOOL_TRUE

    @classmethod
    def write(cls, value: bool) -> bytes:
        return primitives.BOOL_TRUE if value else primitives.BOOL_FALSE
