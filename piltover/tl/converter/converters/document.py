from piltover.tl.converter import ConverterBase
from piltover.tl.types import Document, Document_136


class DocumentConverter(ConverterBase):
    base = Document
    old = [Document_136]
    layers = [136]

    @staticmethod
    def from_136(obj: Document_136) -> Document:
        data = obj.to_dict()
        return Document(**data)

    @staticmethod
    def to_136(obj: Document) -> Document_136:
        data = obj.to_dict()
        return Document_136(**data)
