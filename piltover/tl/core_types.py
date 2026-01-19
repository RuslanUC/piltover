from __future__ import annotations

from collections.abc import Iterable, Sized
from gzip import decompress
from io import BytesIO
from typing import TypeVar, Generic, TYPE_CHECKING

from . import TLObject, Int, Long, Bytes
from .serialization_utils import SerializationUtils

if TYPE_CHECKING:
    from .types import FutureSalt
    from ..context import NeedContextValuesContext


T = TypeVar("T", bound=TLObject)


class Message(TLObject, Generic[T]):
    __tl_id__ = 0x5bb8e511
    __tl_name__ = "Message"

    __slots__ = ("message_id", "seq_no", "obj",)

    def __init__(self, message_id: int, seq_no: int, obj: T):
        self.message_id = message_id
        self.seq_no = seq_no
        self.obj = obj

    @classmethod
    def deserialize(cls, stream: BytesIO) -> Message:
        msg_id = Long.read(stream)
        seq_no = Int.read(stream)
        length = Int.read(stream)
        body = TLObject.read(BytesIO(stream.read(length)))

        return Message(message_id=msg_id, seq_no=seq_no, obj=body)

    def serialize(self) -> bytes:
        body = self.obj.write()
        return Long.write(self.message_id) + Int.write(self.seq_no) + Int.write(len(body)) + body

    @classmethod
    def read(cls, stream: BytesIO, strict_type: bool = False) -> TLObject:
        return Message.deserialize(stream)

    def write(self) -> bytes:
        return self.serialize()


class MsgContainer(TLObject):
    __tl_id__ = 0x73f1f8dc
    __tl_name__ = "MsgContainer"

    __slots__ = ("messages",)

    def __init__(self, messages: list[Message]):
        self.messages = messages

    @classmethod
    def deserialize(cls, stream: BytesIO) -> TLObject:
        count = Int.read(stream)
        result = []

        for _ in range(count):
            result.append(Message.deserialize(stream))

        return MsgContainer(messages=result)

    def serialize(self) -> bytes:
        result = Int.write(len(self.messages))
        for message in self.messages:
            result += message.serialize()
        return result


class RpcResult(TLObject):
    __tl_id__ = 0xf35c6d01
    __tl_name__ = "RpcResult"

    __slots__ = ("req_msg_id", "result",)

    def __init__(self, req_msg_id: int, result: TLObject):
        self.req_msg_id = req_msg_id
        self.result = result

    @classmethod
    def deserialize(cls, stream: BytesIO) -> TLObject:
        req_msg_id = Long.read(stream)
        result = TLObject.read(stream)

        return RpcResult(req_msg_id=req_msg_id, result=result)

    def serialize(self) -> bytes:
        return Long.write(self.req_msg_id) + SerializationUtils.write(self.result)

    def check_for_ctx_values(self, values: NeedContextValuesContext) -> None:
        if isinstance(self.result, Iterable):
            for item in self.result:
                if not isinstance(item, TLObject):
                    return
                item.check_for_ctx_values(values)
        elif isinstance(self.result, TLObject):
            self.result.check_for_ctx_values(values)


class GzipPacked(TLObject):
    __tl_id__ = 0x3072cfa1
    __tl_name__ = "GzipPacked"

    __slots__ = ("packed_data",)

    def __init__(self, packed_data: bytes):
        self.packed_data = packed_data

    @classmethod
    def deserialize(cls, stream: BytesIO) -> TLObject:
        packed_data = Bytes.read(stream)
        decompressed_stream = BytesIO(decompress(packed_data))

        return TLObject.read(decompressed_stream)

    def serialize(self) -> bytes:
        return Bytes.write(self.packed_data)


class FutureSalts(TLObject):
    __tl_id__ = 0xae500895
    __tl_name__ = "FutureSalts"

    __slots__ = ("req_msg_id", "now", "salts",)

    def __init__(self, req_msg_id: int, now: int, salts: list[FutureSalt]):
        self.req_msg_id = req_msg_id
        self.now = now
        self.salts = salts

    @classmethod
    def deserialize(cls, stream: BytesIO) -> TLObject:
        from .types import FutureSalt

        req_msg_id = Long.read(stream)
        now = Int.read(stream)

        count = Int.read(stream)
        salts = []

        for _ in range(count):
            salts.append(FutureSalt.deserialize(stream))

        return FutureSalts(req_msg_id=req_msg_id, now=now, salts=salts)

    def serialize(self) -> bytes:
        result = Long.write(self.req_msg_id)
        result += Int.write(self.now)
        result += Int.write(len(self.salts))

        for salt in self.salts:
            result += salt.serialize()

        return result
