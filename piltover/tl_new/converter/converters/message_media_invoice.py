from piltover.tl_new.types import MessageMediaInvoice, MessageMediaInvoice_136
from piltover.tl_new.converter import ConverterBase


class MessageMediaInvoiceConverter(ConverterBase):
    base = MessageMediaInvoice
    old = [MessageMediaInvoice_136]
    layers = [136]

    @staticmethod
    def from_136(obj: MessageMediaInvoice_136) -> MessageMediaInvoice:
        data = obj.to_dict()
        return MessageMediaInvoice(**data)

    @staticmethod
    def to_136(obj: MessageMediaInvoice) -> MessageMediaInvoice_136:
        data = obj.to_dict()
        del data["extended_media"]
        return MessageMediaInvoice_136(**data)

