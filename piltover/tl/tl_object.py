from __future__ import annotations

from abc import abstractmethod, ABC
from io import BytesIO
from typing import Generic, TypeVar, Self

import piltover.tl as tl
from piltover.exceptions import Error, InvalidConstructorException
from .primitives import Int


class TLObject(ABC):
    __tl_id__: int
    __tl_name__: str

    @classmethod
    def tlid(cls) -> int:
        return cls.__tl_id__

    @classmethod
    def tlname(cls) -> str:
        return cls.__tl_name__

    @abstractmethod
    def serialize(self) -> bytes: ...

    @classmethod
    @abstractmethod
    def deserialize(cls, stream: BytesIO) -> Self: ...

    @classmethod
    def read(cls, stream: BytesIO, strict_type: bool = False) -> Self:
        constructor = Int.read(stream, False)

        if cls is not TLObject:
            if constructor != cls.__tl_id__:
                raise InvalidConstructorException(constructor, True, stream.read())
            return cls.deserialize(stream)

        if constructor not in tl.all.objects:
            raise InvalidConstructorException(constructor, False, stream.read())

        obj = tl.all.objects[constructor].deserialize(stream)

        if strict_type and not isinstance(obj, cls):
            raise Error(f"Expected object type {cls.__name__}, got {obj.__class__.__name__}")

        return obj

    def write(self) -> bytes:
        return Int.write(self.__tl_id__, False) + self.serialize()

    def to_dict(self) -> dict:
        return {slot: getattr(self, slot) for slot in self.__slots__}

    def __repr__(self) -> str:
        fields = []
        for slot in self.__slots__:
            value = getattr(self, slot)
            if self.tlid() in (0xb304a621, 0xde7b673d, 0x96a18d5) and slot == "bytes_" and len(value) > 32:
                value_repr = f"<bytes of length {len(value)}>({value[:32]}...)"
            else:
                value_repr = repr(value)
                if not isinstance(value, TLObject) and value is not None:
                    value_repr = f"{value.__class__.__name__}({value_repr})"
            fields.append(f"{slot}={value_repr}")

        slots = ", ".join(fields)
        return f"{self.__class__.__name__}({slots})"

    def __eq__(self, other: TLObject) -> bool:
        if not isinstance(other, type(self)):
            return False

        for slot in self.__slots__:
            if getattr(self, slot) != getattr(other, slot):
                return False

        return True

    def eq_raise(self, other: TLObject, path: str = "") -> None:
        if not isinstance(other, type(self)):
            raise ValueError(
                f"Failed TLObject equality check at {path or '.'}: "
                f"\"other\" is not an object of type {self.__class__.__name__}"
            )

        for slot in self.__slots__:
            attr_self = getattr(self, slot)
            attr_other = getattr(other, slot)
            if isinstance(attr_self, TLObject):
                attr_self.eq_raise(attr_other, f"{path}.{slot}")
            elif not attr_self and not attr_other:
                continue
            elif attr_self != attr_other:
                raise ValueError(
                    f"Failed TLObject equality check at {path}.{slot}: {attr_self!r} != {attr_other!r}"
                )

    def eq_diff(self, other: TLObject, _inv: bool = False) -> str:
        if not isinstance(other, type(self)):
            this = self
            if _inv:
                this, other = other, this
            return f"<type mismatch, expected \"{this.__class__.__name__}\", got \"{other.__class__.__name__}\">"

        result = ""
        for slot in self.__slots__:
            attr_self = getattr(self, slot)
            attr_other = getattr(other, slot)

            attr_diff = ""
            if isinstance(attr_self, TLObject):
                attr_diff = attr_self.eq_diff(attr_other)
            elif isinstance(attr_other, TLObject):
                attr_diff = attr_other.eq_diff(attr_self, _inv=True)
            elif attr_self != attr_other:
                attr_diff = f"<expected \"{attr_self}\", got \"{attr_other}\">"

            if attr_diff:
                if not result:
                    result += f"{self.__class__.__name__}("
                else:
                    result += ", "
                result += f"{slot} = {attr_diff}"

        if result:
            result += ")"

        return result


T = TypeVar("T")
TObj = TypeVar("TObj", bound=TLObject)


class TLRequest(TLObject, ABC, Generic[T]):
    ...
