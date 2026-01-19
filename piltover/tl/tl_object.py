from __future__ import annotations

from abc import abstractmethod, ABC
from io import BytesIO
from typing import Generic, TypeVar, Self, TYPE_CHECKING

import piltover.tl as tl
from piltover.exceptions import Error, InvalidConstructorException
from .primitives import Int

if TYPE_CHECKING:
    from piltover.context import NeedContextValuesContext


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

    def check_for_ctx_values(self, values: NeedContextValuesContext) -> None:
        ...

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
            if self.tlid() in (0xb304a621, 0xde7b673d, 0x96a18d5) \
                    and slot == "bytes_" and value is not None and len(value) > 32:
                value_repr = f"<bytes of length {len(value)}>({value[:32]}...)"
            elif self.tlid() == 0x768e3aad and slot == "reactions" and len(value) > 4:  # AvailableReactions
                value_repr = f"<reactions of length {len(value)}>"
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


T = TypeVar("T")
TObj = TypeVar("TObj", bound=TLObject)


class TLRequest(TLObject, ABC, Generic[T]):
    ...
