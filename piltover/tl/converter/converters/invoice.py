from piltover.tl.converter import ConverterBase
from piltover.tl.types import Invoice, Invoice_136, Invoice_143


class InvoiceConverter(ConverterBase):
    base = Invoice
    old = [Invoice_136, Invoice_143]
    layers = [136, 143]

    @staticmethod
    def from_136(obj: Invoice_136) -> Invoice:
        data = obj.to_dict()
        return Invoice(**data)

    @staticmethod
    def to_136(obj: Invoice) -> Invoice_136:
        data = obj.to_dict()
        del data["terms_url"]
        del data["recurring"]
        return Invoice_136(**data)

    @staticmethod
    def from_143(obj: Invoice_143) -> Invoice:
        data = obj.to_dict()
        del data["recurring_terms_url"]
        return Invoice(**data)

    @staticmethod
    def to_143(obj: Invoice) -> Invoice_143:
        data = obj.to_dict()
        del data["terms_url"]
        return Invoice_143(**data)
