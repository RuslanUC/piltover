from __future__ import annotations

from gzip import decompress
from io import BytesIO
from typing import TypeVar, Generic

from . import TLObject, Int, Long, Bytes
from .serialization_utils import SerializationUtils

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
    def deserialize(cls, stream) -> Message:
        msg_id = Long.read(stream)
        seq_no = Int.read(stream)
        length = Int.read(stream)
        body = TLObject.read(BytesIO(stream.read(length)))

        return Message(message_id=msg_id, seq_no=seq_no, obj=body)

    def serialize(self) -> bytes:
        body = self.obj.write()
        return Long.write(self.message_id) + Int.write(self.seq_no) + Int.write(len(body)) + body

    @classmethod
    def read(cls, stream, strict_type: bool = False) -> TLObject:
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
    def deserialize(cls, stream) -> TLObject:
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
    def deserialize(cls, stream) -> TLObject:
        req_msg_id = Long.read(stream)
        result = TLObject.read(stream)

        return RpcResult(req_msg_id=req_msg_id, result=result)

    def serialize(self) -> bytes:
        return Long.write(self.req_msg_id) + SerializationUtils.write(self.result)


class GzipPacked(TLObject):
    __tl_id__ = 0x3072cfa1
    __tl_name__ = "GzipPacked"

    __slots__ = ("packed_data",)

    def __init__(self, packed_data: bytes):
        self.packed_data = packed_data

    @classmethod
    def deserialize(cls, stream) -> TLObject:
        packed_data = Bytes.read(stream)
        decompressed_stream = BytesIO(decompress(packed_data))

        return TLObject.read(decompressed_stream)

    def serialize(self) -> bytes:
        return Bytes.write(self.packed_data)
