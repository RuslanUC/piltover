import struct
from typing import Any, TypeVar

from . import primitives
from piltover.exceptions import InvalidConstructorException

T = TypeVar("T")

BOOL_TRUE = b"\xb5\x75\x72\x99"
BOOL_FALSE = b"\x37\x97\x79\xbc"
VECTOR = b"\x15\xc4\xb5\x1c"


class SerializationUtils:
    @staticmethod
    def write(value: Any, int_type: type=None) -> bytes:
        from . import TLObject

        if isinstance(value, int) and not isinstance(value, bool):
            value = int_type(value)

        if isinstance(value, primitives.Int):
            return value.write()
        elif isinstance(value, float):
            return struct.pack("<d", value)
        elif isinstance(value, bool):
            return BOOL_TRUE if value else BOOL_FALSE
        elif isinstance(value, bytes):
            result = b""
            ln = len(value)
            if ln >= 254:
                result += int.to_bytes(254, 1)
                result += int.to_bytes(ln & 0xff, 1)
                result += int.to_bytes((ln >> 8) & 0xff, 1)
                result += int.to_bytes((ln >> 16) & 0xff, 1)
            else:
                result += int.to_bytes(ln, 1)

            result += value
            padding = len(result) % 4
            if padding:
                result += b"\x00" * (4 - padding)

            return result
        elif isinstance(value, str):
            return SerializationUtils.write(value.encode("utf8"))
        elif isinstance(value, TLObject):
            return int.to_bytes(value.__tl_id__, 4, 'little') + value.serialize()
        elif isinstance(value, list):
            result = VECTOR + len(value).to_bytes(4, 'little')
            if isinstance(value, primitives.Vector):
                int_type = value.value_type if issubclass(value.value_type, int) and not isinstance(value, bool) \
                    else int_type
            for v in value:
                result += SerializationUtils.write(v, int_type)
            return result

    @staticmethod
    def read(stream, type_: type[T], subtype: type=None) -> T:
        from . import TLObject, all

        if issubclass(type_, primitives.Int):
            return type_.read(stream)
        elif issubclass(type_, float):
            return struct.unpack("<d", stream.read(8))[0]
        elif issubclass(type_, bool):
            return stream.read(4) == BOOL_TRUE
        elif issubclass(type_, bytes):
            count = stream.read(1)[0]
            offset = 1
            if count >= 254:
                count = stream.read(1)[0] + (stream.read(1)[0] << 8) + (stream.read(1)[0] << 16)
                offset = 4

            result = stream.read(count)
            offset += len(result)
            offset %= 4
            if offset:
                stream.read(4 - offset)

            return result
        elif issubclass(type_, str):
            return SerializationUtils.read(stream, bytes).decode("utf8")
        elif issubclass(type_, TLObject):
            constructor = int.from_bytes(stream.read(4), "little")
            if constructor not in all.objects:
                raise InvalidConstructorException(constructor, stream.read())
            return all.objects[constructor].deserialize(stream)
        elif issubclass(type_, list):
            assert stream.read(4) == VECTOR
            count = SerializationUtils.read(stream, primitives.Int)
            result = []

            for _ in range(count):
                result.append(SerializationUtils.read(stream, subtype))

            return result
