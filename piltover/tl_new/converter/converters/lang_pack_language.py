from piltover.tl_new.converter import ConverterBase
from piltover.tl_new.types import LangPackLanguage, LangPackLanguage_72


class LangPackLanguageConverter(ConverterBase):
    base = LangPackLanguage
    old = [LangPackLanguage_72]
    layers = [72]

    @staticmethod
    def from_72(obj: LangPackLanguage_72) -> LangPackLanguage:
        data = obj.to_dict()
        data["strings_count"] = 0
        data["plural_code"] = ""
        data["translated_count"] = 0
        data["translations_url"] = ""
        return LangPackLanguage(**data)

    @staticmethod
    def to_72(obj: LangPackLanguage) -> LangPackLanguage_72:
        data = obj.to_dict()
        del data["strings_count"]
        del data["beta"]
        del data["plural_code"]
        del data["flags"]
        del data["official"]
        del data["translated_count"]
        del data["rtl"]
        del data["translations_url"]
        del data["base_lang_code"]
        return LangPackLanguage_72(**data)
