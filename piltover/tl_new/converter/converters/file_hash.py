from piltover.tl_new.converter import ConverterBase
from piltover.tl_new.types import FileHash, FileHash_136


class FileHashConverter(ConverterBase):
    base = FileHash
    old = [FileHash_136]
    layers = [136]

    @staticmethod
    def from_136(obj: FileHash_136) -> FileHash:
        data = obj.to_dict()
        return FileHash(**data)

    @staticmethod
    def to_136(obj: FileHash) -> FileHash_136:
        data = obj.to_dict()
        return FileHash_136(**data)
