from piltover.tl_new.types import EncryptedFile, EncryptedFile_136
from piltover.tl_new.converter import ConverterBase


class EncryptedFileConverter(ConverterBase):
    base = EncryptedFile
    old = [EncryptedFile_136]
    layers = [136]

    @staticmethod
    def from_136(obj: EncryptedFile_136) -> EncryptedFile:
        data = obj.to_dict()
        return EncryptedFile(**data)

    @staticmethod
    def to_136(obj: EncryptedFile) -> EncryptedFile_136:
        data = obj.to_dict()
        return EncryptedFile_136(**data)

