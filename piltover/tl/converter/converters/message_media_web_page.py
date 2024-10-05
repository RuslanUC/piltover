from piltover.tl.converter import ConverterBase
from piltover.tl.types import MessageMediaWebPage, MessageMediaWebPage_136


class MessageMediaWebPageConverter(ConverterBase):
    base = MessageMediaWebPage
    old = [MessageMediaWebPage_136]
    layers = [136]

    @staticmethod
    def from_136(obj: MessageMediaWebPage_136) -> MessageMediaWebPage:
        data = obj.to_dict()
        return MessageMediaWebPage(**data)

    @staticmethod
    def to_136(obj: MessageMediaWebPage) -> MessageMediaWebPage_136:
        data = obj.to_dict()
        del data["safe"]
        del data["force_large_media"]
        del data["manual"]
        del data["flags"]
        del data["force_small_media"]
        return MessageMediaWebPage_136(**data)
