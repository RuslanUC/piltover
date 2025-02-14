from __future__ import annotations

from abc import abstractmethod, ABC
from io import BytesIO

from piltover.exceptions import Error
from .primitives import Int
from .serialization_utils import SerializationUtils


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
    def deserialize(cls, stream: BytesIO) -> TLObject: ...

    @classmethod
    def read(cls, stream: BytesIO, strict_type: bool = False) -> TLObject:
        obj = SerializationUtils.read(stream, cls)
        if strict_type and not isinstance(obj, cls):
            raise Error(f"Expected object type {cls.__name__}, got {obj.__class__.__name__}")
        return obj

    def write(self) -> bytes:
        return Int.write(self.__tl_id__, False) + self.serialize()

    def to_dict(self) -> dict:
        return {slot: getattr(self, slot) for slot in self.__slots__}

    def __repr__(self) -> str:
        slots = ", ".join([f"{slot}={getattr(self, slot)!r}" for slot in self.__slots__])
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
