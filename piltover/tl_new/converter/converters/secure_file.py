from piltover.tl_new.converter import ConverterBase
from piltover.tl_new.types import SecureFile, SecureFile_136


class SecureFileConverter(ConverterBase):
    base = SecureFile
    old = [SecureFile_136]
    layers = [136]

    @staticmethod
    def from_136(obj: SecureFile_136) -> SecureFile:
        data = obj.to_dict()
        return SecureFile(**data)

    @staticmethod
    def to_136(obj: SecureFile) -> SecureFile_136:
        data = obj.to_dict()
        return SecureFile_136(**data)
