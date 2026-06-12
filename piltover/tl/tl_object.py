from __future__ import annotations

import asyncio
from abc import abstractmethod, ABC
from io import BytesIO
from typing import Generic, TypeVar, Self, TYPE_CHECKING

import piltover.tl as tl
from piltover.exceptions import Error, InvalidConstructorException, UnknownConstructorException
from .primitives import Int
from .serialization_context import SerializationContext, EMPTY_SERIALIZATION_CONTEXT
from .tl_worker import TL_WORKER

if TYPE_CHECKING:
    from piltover.context import NeedContextValuesContext


class TLObject(ABC):
    __tl_id__: int
    __tl_name__: str
    __tl_layer__: int

    @classmethod
    def tlid(cls) -> int:
        return cls.__tl_id__

    @classmethod
    def tlname(cls) -> str:
        return cls.__tl_name__

    @classmethod
    def tllayer(cls) -> int:
        return cls.__tl_layer__

    @abstractmethod
    def serialize(self, ctx: SerializationContext = EMPTY_SERIALIZATION_CONTEXT) -> bytes: ...

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
                raise InvalidConstructorException(constructor, stream.read())
            return cls.deserialize(stream)

        if constructor not in tl.all.objects:
            raise UnknownConstructorException(constructor, stream.read())

        obj = tl.all.objects[constructor].deserialize(stream)

        if strict_type and not isinstance(obj, cls):
            raise Error(f"Expected object type {cls.__name__}, got {obj.__class__.__name__}")

        return obj

    def write(self, ctx: SerializationContext = EMPTY_SERIALIZATION_CONTEXT) -> bytes:
        return Int.write(self.__tl_id__, False) + self.serialize(ctx)

    @classmethod
    async def read_in_worker(cls, stream: BytesIO, strict_type: bool = False) -> Self:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(TL_WORKER, cls.read, stream, strict_type)

    async def write_in_worker(self, ctx: SerializationContext = EMPTY_SERIALIZATION_CONTEXT) -> bytes:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(TL_WORKER, self.write, ctx)

    def to_dict(self) -> dict:
        return {slot: getattr(self, slot) for slot in self.__slots__}

    def __repr__(self) -> str:
        fields = []
        slots = set()

        for cls in self.__class__.mro():
            slots.update(getattr(cls, "__slots__", ()))

        for slot in slots:
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
