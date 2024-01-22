from piltover.tl_new.functions.messages import SendMessage, SendMessage_136, SendMessage_148
from piltover.tl_new.converter import ConverterBase


class SendMessageConverter(ConverterBase):
    base = SendMessage
    old = [SendMessage_136, SendMessage_148]
    layers = [136, 148]

    @staticmethod
    def from_136(obj: SendMessage_136) -> SendMessage:
        data = obj.to_dict()
        del data["reply_to_msg_id"]
        return SendMessage(**data)

    @staticmethod
    def to_136(obj: SendMessage) -> SendMessage_136:
        data = obj.to_dict()
        del data["reply_to"]
        del data["update_stickersets_order"]
        del data["invert_media"]
        return SendMessage_136(**data)

    @staticmethod
    def from_148(obj: SendMessage_148) -> SendMessage:
        data = obj.to_dict()
        del data["top_msg_id"]
        del data["reply_to_msg_id"]
        return SendMessage(**data)

    @staticmethod
    def to_148(obj: SendMessage) -> SendMessage_148:
        data = obj.to_dict()
        del data["reply_to"]
        del data["invert_media"]
        return SendMessage_148(**data)

