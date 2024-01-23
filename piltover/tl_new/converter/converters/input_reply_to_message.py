from piltover.tl_new.converter import ConverterBase
from piltover.tl_new.types import InputReplyToMessage, InputReplyToMessage_160, InputReplyToMessage_166


class InputReplyToMessageConverter(ConverterBase):
    base = InputReplyToMessage
    old = [InputReplyToMessage_160, InputReplyToMessage_166]
    layers = [160, 166]

    @staticmethod
    def from_160(obj: InputReplyToMessage_160) -> InputReplyToMessage:
        data = obj.to_dict()
        return InputReplyToMessage(**data)

    @staticmethod
    def to_160(obj: InputReplyToMessage) -> InputReplyToMessage_160:
        data = obj.to_dict()
        del data["quote_entities"]
        del data["reply_to_peer_id"]
        del data["quote_text"]
        del data["quote_offset"]
        return InputReplyToMessage_160(**data)

    @staticmethod
    def from_166(obj: InputReplyToMessage_166) -> InputReplyToMessage:
        data = obj.to_dict()
        return InputReplyToMessage(**data)

    @staticmethod
    def to_166(obj: InputReplyToMessage) -> InputReplyToMessage_166:
        data = obj.to_dict()
        del data["quote_offset"]
        return InputReplyToMessage_166(**data)
