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
        return SerializationUtils.write(self.__tl_id__, Int) + self.serialize()

    def to_dict(self) -> dict:
        return {slot: getattr(self, slot) for slot in self.__slots__}

    def __repr__(self) -> str:
        slots = ", ".join([f"{slot}={getattr(self, slot)!r}" for slot in self.__slots__])
        return f"{self.__class__.__name__}({slots})"
