from piltover.tl_new.types import MessageActionBotAllowed, MessageActionBotAllowed_136
from piltover.tl_new.converter import ConverterBase


class MessageActionBotAllowedConverter(ConverterBase):
    base = MessageActionBotAllowed
    old = [MessageActionBotAllowed_136]
    layers = [136]

    @staticmethod
    def from_136(obj: MessageActionBotAllowed_136) -> MessageActionBotAllowed:
        data = obj.to_dict()
        return MessageActionBotAllowed(**data)

    @staticmethod
    def to_136(obj: MessageActionBotAllowed) -> MessageActionBotAllowed_136:
        data = obj.to_dict()
        del data["app"]
        del data["from_request"]
        del data["flags"]
        del data["attach_menu"]
        if data["domain"] is None:
            data["domain"] = ""
        return MessageActionBotAllowed_136(**data)

