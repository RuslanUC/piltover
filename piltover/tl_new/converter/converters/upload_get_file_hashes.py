from piltover.tl_new.functions.upload import GetFileHashes, GetFileHashes_136
from piltover.tl_new.converter import ConverterBase


class GetFileHashesConverter(ConverterBase):
    base = GetFileHashes
    old = [GetFileHashes_136]
    layers = [136]

    @staticmethod
    def from_136(obj: GetFileHashes_136) -> GetFileHashes:
        data = obj.to_dict()
        return GetFileHashes(**data)

    @staticmethod
    def to_136(obj: GetFileHashes) -> GetFileHashes_136:
        data = obj.to_dict()
        return GetFileHashes_136(**data)

