from piltover.tl_new.converter import ConverterBase
from piltover.tl_new.types import CodeSettings, CodeSettings_136


class CodeSettingsConverter(ConverterBase):
    base = CodeSettings
    old = [CodeSettings_136]
    layers = [136]

    @staticmethod
    def from_136(obj: CodeSettings_136) -> CodeSettings:
        data = obj.to_dict()
        return CodeSettings(**data)

    @staticmethod
    def to_136(obj: CodeSettings) -> CodeSettings_136:
        data = obj.to_dict()
        del data["token"]
        del data["allow_firebase"]
        del data["app_sandbox"]
        return CodeSettings_136(**data)
