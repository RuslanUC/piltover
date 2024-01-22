from piltover.tl_new.functions.messages import ForwardMessages, ForwardMessages_136
from piltover.tl_new.converter import ConverterBase


class ForwardMessagesConverter(ConverterBase):
    base = ForwardMessages
    old = [ForwardMessages_136]
    layers = [136]

    @staticmethod
    def from_136(obj: ForwardMessages_136) -> ForwardMessages:
        data = obj.to_dict()
        return ForwardMessages(**data)

    @staticmethod
    def to_136(obj: ForwardMessages) -> ForwardMessages_136:
        data = obj.to_dict()
        del data["top_msg_id"]
        return ForwardMessages_136(**data)

