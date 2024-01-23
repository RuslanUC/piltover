from piltover.tl_new.converter import ConverterBase
from piltover.tl_new.functions.upload import GetFile, GetFile_136


class GetFileConverter(ConverterBase):
    base = GetFile
    old = [GetFile_136]
    layers = [136]

    @staticmethod
    def from_136(obj: GetFile_136) -> GetFile:
        data = obj.to_dict()
        return GetFile(**data)

    @staticmethod
    def to_136(obj: GetFile) -> GetFile_136:
        data = obj.to_dict()
        return GetFile_136(**data)
