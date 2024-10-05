from piltover.tl.converter import ConverterBase
from piltover.tl.types import InputMediaInvoice, InputMediaInvoice_136


class InputMediaInvoiceConverter(ConverterBase):
    base = InputMediaInvoice
    old = [InputMediaInvoice_136]
    layers = [136]

    @staticmethod
    def from_136(obj: InputMediaInvoice_136) -> InputMediaInvoice:
        data = obj.to_dict()
        return InputMediaInvoice(**data)

    @staticmethod
    def to_136(obj: InputMediaInvoice) -> InputMediaInvoice_136:
        data = obj.to_dict()
        del data["extended_media"]
        return InputMediaInvoice_136(**data)
