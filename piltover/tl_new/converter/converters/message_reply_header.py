from piltover.tl_new.types import MessageReplyHeader, MessageReplyHeader_136, MessageReplyHeader_166
from piltover.tl_new.converter import ConverterBase


class MessageReplyHeaderConverter(ConverterBase):
    base = MessageReplyHeader
    old = [MessageReplyHeader_136, MessageReplyHeader_166]
    layers = [136, 166]

    @staticmethod
    def from_136(obj: MessageReplyHeader_136) -> MessageReplyHeader:
        data = obj.to_dict()
        return MessageReplyHeader(**data)

    @staticmethod
    def to_136(obj: MessageReplyHeader) -> MessageReplyHeader_136:
        data = obj.to_dict()
        del data["quote_text"]
        del data["reply_from"]
        del data["reply_media"]
        del data["quote_entities"]
        del data["quote_offset"]
        del data["quote"]
        del data["forum_topic"]
        if data["reply_to_msg_id"] is None:
            data["reply_to_msg_id"] = 0
        return MessageReplyHeader_136(**data)

    @staticmethod
    def from_166(obj: MessageReplyHeader_166) -> MessageReplyHeader:
        data = obj.to_dict()
        return MessageReplyHeader(**data)

    @staticmethod
    def to_166(obj: MessageReplyHeader) -> MessageReplyHeader_166:
        data = obj.to_dict()
        del data["quote_offset"]
        return MessageReplyHeader_166(**data)

