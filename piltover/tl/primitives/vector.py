from __future__ import annotations

from abc import abstractmethod, ABC
from array import array
from io import BytesIO
from typing import Literal, cast, TypeVar, TYPE_CHECKING, Protocol

from piltover.exceptions import InvalidConstructorException
from piltover.tl import primitives
from piltover.utils.utils import classinstancemethod

if TYPE_CHECKING:
    from piltover.tl import TLObject


T = TypeVar("T")


class Vector(list[T], ABC):
    @classmethod
    @abstractmethod
    def read(cls, stream: BytesIO) -> array[int]:
        ...

    @abstractmethod
    def write(self) -> bytes:
        ...

    @classmethod
    def check_constructor(cls, stream: BytesIO) -> None:
        if (constructor := stream.read(4)) != primitives.VECTOR:
            raise InvalidConstructorException(constructor, False, stream.read())

    @classmethod
    def read_header(cls, stream: BytesIO) -> int:
        cls.check_constructor(stream)
        return primitives.Int.read(stream)

    @classmethod
    def header(cls, count: int) -> bytes:
        return primitives.VECTOR + primitives.Int.write(count)


class PrimitiveVector(Vector[T], ABC):
    ARRAY_TYPE: Literal["b", "B", "h", "H", "i", "I", "l", "L", "q", "Q"]
    ELEMENT_SIZE: Literal[4, 8]

    @classmethod
    def read(cls, stream: BytesIO) -> array[T]:
        count = cls.read_header(stream)
        arr = array(cls.ARRAY_TYPE, stream.read(count * cls.ELEMENT_SIZE))
        return cast(T, arr)

    # noinspection PyMethodParameters
    @classinstancemethod
    def write(cls: type[PrimitiveVector[T]], self: list[T]) -> bytes:
        arr = array(cls.ARRAY_TYPE, self)
        return cls.header(len(self)) + arr.tobytes()


class IntVector(PrimitiveVector[int]):
    ARRAY_TYPE = "i"
    ELEMENT_SIZE = primitives.Int.SIZE


class LongVector(PrimitiveVector[int]):
    ARRAY_TYPE = "q"
    ELEMENT_SIZE = primitives.Long.SIZE


class FloatVector(PrimitiveVector[float]):
    ARRAY_TYPE = "d"
    ELEMENT_SIZE = 8


class _Primitive(Protocol):
    @classmethod
    def read(cls, stream: BytesIO) -> T:
        ...

    @classmethod
    def write(cls, value: T) -> bytes:
        ...


class _Vector(Vector[T], ABC):
    ELEMENT_TYPE: type[_Primitive[T]]

    @classmethod
    def read(cls, stream: BytesIO) -> list[T]:
        count = cls.read_header(stream)
        return cls(cls.ELEMENT_TYPE.read(stream) for _ in range(count))

    # noinspection PyMethodParameters
    @classinstancemethod
    def write(cls: type[_Vector[T]], self: list[T]) -> bytes:
        result = cls.header(len(self))
        for element in self:
            result += cls.ELEMENT_TYPE.write(element)
        return result


class Int128Vector(_Vector[int]):
    ELEMENT_TYPE = primitives.Int128


class Int256Vector(_Vector[int]):
    ELEMENT_TYPE = primitives.Int256


class BoolVector(_Vector[bool]):
    ELEMENT_TYPE = primitives.Bool


class BytesVector(_Vector[bytes]):
    ELEMENT_TYPE = primitives.Bytes


class StringVector(_Vector[str]):
    ELEMENT_TYPE = primitives.String


class TLObjectVector(Vector["TLObject"]):
    @classmethod
    def read(cls, stream: BytesIO) -> list[TLObject]:
        from piltover.tl import TLObject
        count = cls.read_header(stream)
        return cls(TLObject.read(stream) for _ in range(count))

    # noinspection PyMethodParameters
    @classinstancemethod
    def write(cls: type[TLObjectVector], self: list[TLObject]) -> bytes:
        result = cls.header(len(self))
        for element in self:
            result += element.write()
        return result
