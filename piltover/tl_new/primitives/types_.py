from io import BytesIO

from piltover import tl_new
from piltover.tl_new import TLField, TLObject, tl_object, Int, Long, SerializationUtils


@tl_object(id=0x5bb8e511, name="Message")
class Message(TLObject):
    message_id: Long = TLField()
    seq_no: Int = TLField()
    obj: TLObject = TLField()

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
