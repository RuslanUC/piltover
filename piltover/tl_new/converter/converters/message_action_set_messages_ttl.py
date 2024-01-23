from piltover.tl_new.converter import ConverterBase
from piltover.tl_new.types import MessageActionSetMessagesTTL, MessageActionSetMessagesTTL_136


class MessageActionSetMessagesTTLConverter(ConverterBase):
    base = MessageActionSetMessagesTTL
    old = [MessageActionSetMessagesTTL_136]
    layers = [136]

    @staticmethod
    def from_136(obj: MessageActionSetMessagesTTL_136) -> MessageActionSetMessagesTTL:
        data = obj.to_dict()
        return MessageActionSetMessagesTTL(**data)

    @staticmethod
    def to_136(obj: MessageActionSetMessagesTTL) -> MessageActionSetMessagesTTL_136:
        data = obj.to_dict()
        del data["auto_setting_from"]
        del data["flags"]
        return MessageActionSetMessagesTTL_136(**data)
