from piltover.tl_new.converter import ConverterBase
from piltover.tl_new.types import GlobalPrivacySettings, GlobalPrivacySettings_136


class GlobalPrivacySettingsConverter(ConverterBase):
    base = GlobalPrivacySettings
    old = [GlobalPrivacySettings_136]
    layers = [136]

    @staticmethod
    def from_136(obj: GlobalPrivacySettings_136) -> GlobalPrivacySettings:
        data = obj.to_dict()
        return GlobalPrivacySettings(**data)

    @staticmethod
    def to_136(obj: GlobalPrivacySettings) -> GlobalPrivacySettings_136:
        data = obj.to_dict()
        del data["keep_archived_unmuted"]
        del data["keep_archived_folders"]
        return GlobalPrivacySettings_136(**data)
