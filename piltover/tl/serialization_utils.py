import struct
import sys
from array import array
from io import BytesIO
from typing import Any, TypeVar

from piltover.exceptions import InvalidConstructorException
from . import primitives

T = TypeVar("T")

BOOL_TRUE = b"\xb5\x75\x72\x99"
BOOL_FALSE = b"\x37\x97\x79\xbc"
VECTOR = b"\x15\xc4\xb5\x1c"

primitive_array_types = {
    primitives.Int: ("i", 4),
    primitives.Long: ("q", 8),
    float: ("d", 8),
}

for __array_type, __itemsize_expected in primitive_array_types.values():
    __itemsize_actual = array(__array_type).itemsize
    if __itemsize_actual != __itemsize_expected:
        raise RuntimeError(
            f"Expected \"{__array_type}\" array item size to be {__itemsize_expected}, got {__itemsize_actual}"
        )


class SerializationUtils:
    DOUBLE_STRUCT_FMT = struct.Struct("<d")

    @staticmethod
    def write(value: Any, int_type: type=None) -> bytes:
        from . import TLObject

        if isinstance(value, int) and not isinstance(value, (bool, primitives.Int)):
            value = int_type(value)

        if isinstance(value, primitives.Int):
            return value.write()
        elif isinstance(value, float):
            return SerializationUtils.DOUBLE_STRUCT_FMT.pack(value)
        elif isinstance(value, bool):
            return BOOL_TRUE if value else BOOL_FALSE
        elif isinstance(value, bytes):
            result = b""
            ln = len(value)
            if ln >= 254:
                result += bytes([254])
                result += int.to_bytes(ln, 3, "little")
            else:
                result += bytes([ln])

            result += value
            padding = len(result) % 4
            if padding:
                result += b"\x00" * (4 - padding)

            return result
        elif isinstance(value, str):
            return SerializationUtils.write(value.encode("utf8"))
        elif isinstance(value, TLObject):
            return value.write()
        elif isinstance(value, list):
            result = VECTOR + primitives.Int.write(len(value))
            if isinstance(value, primitives.Vector) \
                    and issubclass(value.value_type, int) \
                    and not isinstance(value, bool):
                int_type = value.value_type

            if int_type in primitive_array_types or type(value) in primitive_array_types:
                t = int_type if int_type in primitive_array_types else type(value)

                array_type, _ = primitive_array_types[t]
                arr = array(array_type, value)
                if sys.byteorder != "little":
                    arr.byteswap()
                return result + arr.tobytes()

            for v in value:
                result += SerializationUtils.write(v, int_type)

            return result
        elif isinstance(value, array):
            if sys.byteorder != "little":
               value.byteswap()
            result = VECTOR + primitives.Int.write(len(value)) + value.tobytes()
            if sys.byteorder != "little":
                value.byteswap()
            return result
        else:
            raise TypeError(f"Unknown type: {type(value)}")

    @staticmethod
    def read(stream: BytesIO, type_: type[T], subtype: type = None) -> T:
        from . import TLObject, all

        if issubclass(type_, primitives.Int):
            return type_.read(stream)
        elif issubclass(type_, float):
            return SerializationUtils.DOUBLE_STRUCT_FMT.unpack(stream.read(8))[0]
        elif issubclass(type_, bool):
            return stream.read(4) == BOOL_TRUE
        elif issubclass(type_, bytes):
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
        elif issubclass(type_, str):
            return SerializationUtils.read(stream, bytes).decode("utf8")
        elif issubclass(type_, TLObject):
            constructor = primitives.Int.read(stream, False)
            if constructor not in all.objects:
                raise InvalidConstructorException(constructor, False, stream.read())
            return all.objects[constructor].deserialize(stream)
        elif issubclass(type_, list):
            if (constructor := stream.read(4)) != VECTOR:
                raise InvalidConstructorException(constructor, False, stream.read())
            count = SerializationUtils.read(stream, primitives.Int)
            result = []

            if subtype in primitive_array_types:
                array_type, item_size = primitive_array_types[subtype]
                arr = array(array_type, stream.read(count * item_size))
                if sys.byteorder != "little":
                    arr.byteswap()
                return arr

            for _ in range(count):
                result.append(SerializationUtils.read(stream, subtype))

            return result
        else:
            raise TypeError(f"Unknown type: {type_}")
