from piltover.tl_new.functions.upload import GetCdnFileHashes, GetCdnFileHashes_136
from piltover.tl_new.converter import ConverterBase


class GetCdnFileHashesConverter(ConverterBase):
    base = GetCdnFileHashes
    old = [GetCdnFileHashes_136]
    layers = [136]

    @staticmethod
    def from_136(obj: GetCdnFileHashes_136) -> GetCdnFileHashes:
        data = obj.to_dict()
        return GetCdnFileHashes(**data)

    @staticmethod
    def to_136(obj: GetCdnFileHashes) -> GetCdnFileHashes_136:
        data = obj.to_dict()
        return GetCdnFileHashes_136(**data)

