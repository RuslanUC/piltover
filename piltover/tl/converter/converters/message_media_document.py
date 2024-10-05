from piltover.tl.converter import ConverterBase
from piltover.tl.types import MessageMediaDocument, MessageMediaDocument_136


class MessageMediaDocumentConverter(ConverterBase):
    base = MessageMediaDocument
    old = [MessageMediaDocument_136]
    layers = [136]

    @staticmethod
    def from_136(obj: MessageMediaDocument_136) -> MessageMediaDocument:
        data = obj.to_dict()
        return MessageMediaDocument(**data)

    @staticmethod
    def to_136(obj: MessageMediaDocument) -> MessageMediaDocument_136:
        data = obj.to_dict()
        del data["spoiler"]
        del data["nopremium"]
        del data["alt_document"]
        return MessageMediaDocument_136(**data)
