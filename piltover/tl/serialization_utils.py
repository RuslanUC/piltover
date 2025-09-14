import sys
from array import array
from io import BytesIO
from typing import Any, TypeVar

from . import primitives

T = TypeVar("T")

primitive_array_types = [
    ("i", 4),
    ("q", 8),
    ("d", 8),
]

for __array_type, __itemsize_expected in primitive_array_types:
    __itemsize_actual = array(__array_type).itemsize
    if __itemsize_actual != __itemsize_expected:
        raise RuntimeError(
            f"Expected \"{__array_type}\" array item size to be {__itemsize_expected}, got {__itemsize_actual}"
        )


if sys.byteorder != "little":
    raise RuntimeError(f"\"{sys.byteorder}\" byteorder is not currently supported")


class SerializationUtils:
    @staticmethod
    def write(value: Any) -> bytes:
        from . import TLObject

        if isinstance(value, int) and not isinstance(value, (bool, primitives.Int)):
            raise TypeError("SerializationUtils got raw int which is not supported. Use one of primitives.Int* types.")

        if isinstance(value, primitives.Int):
            return value.write()
        elif isinstance(value, float):
            return primitives.Float.write(value)
        elif isinstance(value, bool):
            return primitives.BOOL_TRUE if value else primitives.BOOL_FALSE
        elif isinstance(value, bytes):
            return primitives.Bytes.write(value)
        elif isinstance(value, str):
            return primitives.String.write(value)
        elif isinstance(value, TLObject):
            return value.write()
        elif isinstance(value, list) and not isinstance(value, primitives.Vector):
            raise TypeError(f"Writing raw lists is not supported. Use primitives.Vector* types.")
        elif isinstance(value, primitives.Vector):
            return value.write()
        elif isinstance(value, array):
            return primitives.VECTOR + primitives.Int.write(len(value)) + value.tobytes()
        else:
            raise TypeError(f"Unknown type: {type(value)}")

    @staticmethod
    def read(stream: BytesIO, type_: type[T]) -> T:
        from . import TLObject

        if issubclass(type_, primitives.Int):
            return type_.read(stream)
        elif issubclass(type_, float):
            return primitives.Float.read(stream)
        elif issubclass(type_, bool):
            return stream.read(4) == primitives.BOOL_TRUE
        elif issubclass(type_, bytes):
            return primitives.Bytes.read(stream)
        elif issubclass(type_, str):
            return primitives.String.read(stream)
        elif issubclass(type_, TLObject):
            return TLObject.read(stream)
        elif issubclass(type_, list) and not issubclass(type_, primitives.Vector):
            raise TypeError(f"Reading raw lists is not supported. Use primitives.Vector* types.")
        elif issubclass(type_, primitives.Vector):
            return type_.read(stream)
        else:
            raise TypeError(f"Unknown type: {type_}")
