from gzip import decompress
from io import BytesIO
from typing import TypeVar, Generic

from piltover import tl_new
from piltover.tl_new import TLField, TLObject, tl_object, Int, Long, SerializationUtils

T = TypeVar("T", bound=TLObject)


@tl_object(id=0x5bb8e511, name="Message")
class Message(TLObject, Generic[T]):
    message_id: Long = TLField()
    seq_no: Int = TLField()
    obj: T = TLField()

    @classmethod
    def deserialize(cls, stream) -> TLObject:
        msg_id = Long.read(stream)
        seq_no = Int.read(stream)
        length = Int.read(stream)
        body = SerializationUtils.read(BytesIO(stream.read(length)), TLObject)

        return Message(message_id=msg_id, seq_no=seq_no, obj=body)

    def serialize(self) -> bytes:
        body = SerializationUtils.write(self.obj)
        return Long.write(self.message_id) + Int.write(self.seq_no) + Int.write(len(body)) + body


@tl_object(id=0x73f1f8dc, name="MsgContainer")
class MsgContainer(TLObject):
    messages: list[Message] = TLField()

    @classmethod
    def deserialize(cls, stream) -> TLObject:
        count = SerializationUtils.read(stream, tl_new.primitives.Int)
        result = []

        for _ in range(count):
            result.append(Message.deserialize(stream))

        return MsgContainer(messages=result)

    def serialize(self) -> bytes:
        result = len(self.messages).to_bytes(4, 'little')
        for message in self.messages:
            result += SerializationUtils.write(message, None)
        return result


@tl_object(id=0xf35c6d01, name="RpcResult")
class RpcResult(TLObject):
    req_msg_id: Long = TLField()
    result: TLObject = TLField()


@tl_object(id=0x3072cfa1, name="GzipPacked")
class GzipPacked(TLObject):
    packed_data: bytes = TLField()

    @classmethod
    def deserialize(cls, stream) -> TLObject:
        packed_data = SerializationUtils.read(stream, bytes)
        decompressed_stream = BytesIO(decompress(packed_data))

        return SerializationUtils.read(decompressed_stream, TLObject)


class SerializedObject(TLObject):
    def __init__(self, serialized_data: bytes):
        super().__init__()
        self.__tl_id__ = int.from_bytes(serialized_data[:4], "little")
        self._data = serialized_data

    def serialize(self) -> bytes:
        return self._data[4:]

    @classmethod
    def deserialize(cls, stream) -> TLObject:
        raise RuntimeError("SerializedObject.deserialize should not be called")

    #def __repr__(self):
    #    return repr(TLObject.read(BytesIO(self._data)))
