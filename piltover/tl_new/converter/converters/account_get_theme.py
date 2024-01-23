from piltover.tl_new.converter import ConverterBase
from piltover.tl_new.functions.account import GetTheme, GetTheme_136


class GetThemeConverter(ConverterBase):
    base = GetTheme
    old = [GetTheme_136]
    layers = [136]

    @staticmethod
    def from_136(obj: GetTheme_136) -> GetTheme:
        data = obj.to_dict()
        del data["document_id"]
        return GetTheme(**data)

    @staticmethod
    def to_136(obj: GetTheme) -> GetTheme_136:
        data = obj.to_dict()
        data["document_id"] = 0  # Method should not be downgraded
        return GetTheme_136(**data)
