from piltover.tl.converter import ConverterBase
from piltover.tl.types import DraftMessage, DraftMessage_136


class DraftMessageConverter(ConverterBase):
    base = DraftMessage
    old = [DraftMessage_136]
    layers = [136]

    @staticmethod
    def from_136(obj: DraftMessage_136) -> DraftMessage:
        data = obj.to_dict()
        del data["reply_to_msg_id"]
        return DraftMessage(**data)

    @staticmethod
    def to_136(obj: DraftMessage) -> DraftMessage_136:
        data = obj.to_dict()
        del data["invert_media"]
        del data["reply_to"]
        del data["media"]
        return DraftMessage_136(**data)
