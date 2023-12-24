from piltover.tl_new import TLField, TLObject, tl_object, Int, Long


@tl_object(id=0x5bb8e511, name="Message")
class Message(TLObject):
    msg_id: Long = TLField()
    seqno: Int = TLField()
    bytes: Int = TLField()
    body: TLObject = TLField()


@tl_object(id=0x73f1f8dc, name="MsgContainer")
class MsgContainer(TLObject):
    messages: list[Message] = TLField()


@tl_object(id=0xf35c6d01, name="RpcResult")
class RpcResult(TLObject):
    req_msg_id: Long = TLField()
    result: TLObject = TLField()
