from piltover.tl_new.converter import ConverterBase
from piltover.tl_new.functions.langpack import GetLanguages, GetLanguages_72


class GetLanguagesConverter(ConverterBase):
    base = GetLanguages
    old = [GetLanguages_72]
    layers = [72]

    @staticmethod
    def from_72(obj: GetLanguages_72) -> GetLanguages:
        data = obj.to_dict()
        data["lang_pack"] = ""
        return GetLanguages(**data)

    @staticmethod
    def to_72(obj: GetLanguages) -> GetLanguages_72:
        data = obj.to_dict()
        del data["lang_pack"]
        return GetLanguages_72(**data)
