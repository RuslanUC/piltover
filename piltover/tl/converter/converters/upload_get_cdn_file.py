from piltover.tl.converter import ConverterBase
from piltover.tl.functions.upload import GetCdnFile, GetCdnFile_136


class GetCdnFileConverter(ConverterBase):
    base = GetCdnFile
    old = [GetCdnFile_136]
    layers = [136]

    @staticmethod
    def from_136(obj: GetCdnFile_136) -> GetCdnFile:
        data = obj.to_dict()
        return GetCdnFile(**data)

    @staticmethod
    def to_136(obj: GetCdnFile) -> GetCdnFile_136:
        data = obj.to_dict()
        return GetCdnFile_136(**data)
