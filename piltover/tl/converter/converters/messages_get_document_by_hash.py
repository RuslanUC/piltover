from piltover.tl.converter import ConverterBase
from piltover.tl.functions.messages import GetDocumentByHash, GetDocumentByHash_136


class GetDocumentByHashConverter(ConverterBase):
    base = GetDocumentByHash
    old = [GetDocumentByHash_136]
    layers = [136]

    @staticmethod
    def from_136(obj: GetDocumentByHash_136) -> GetDocumentByHash:
        data = obj.to_dict()
        return GetDocumentByHash(**data)

    @staticmethod
    def to_136(obj: GetDocumentByHash) -> GetDocumentByHash_136:
        data = obj.to_dict()
        return GetDocumentByHash_136(**data)
