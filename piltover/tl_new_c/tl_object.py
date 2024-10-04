from __future__ import annotations

from abc import abstractmethod, ABC

from piltover.exceptions import Error
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
    def deserialize(cls, stream) -> TLObject: ...

    @classmethod
    def read(cls, stream, strict_type: bool = False) -> TLObject:
        obj = SerializationUtils.read(stream, cls)
        if strict_type and not isinstance(obj, cls):
            raise Error(f"Expected object type {cls.__name__}, got {obj.__class__.__name__}")
        return obj

    def write(self) -> bytes:
        return SerializationUtils.write(self.__tl_id__) + self.serialize()

    def to_dict(self) -> dict:
        return {slot: getattr(self, slot) for slot in self.__slots__}
