from piltover.tl_new.converter import ConverterBase
from piltover.tl_new.types import AutoDownloadSettings, AutoDownloadSettings_136, AutoDownloadSettings_143


class AutoDownloadSettingsConverter(ConverterBase):
    base = AutoDownloadSettings
    old = [AutoDownloadSettings_136, AutoDownloadSettings_143]
    layers = [136, 143]

    @staticmethod
    def from_136(obj: AutoDownloadSettings_136) -> AutoDownloadSettings:
        data = obj.to_dict()
        data["small_queue_active_operations_max"] = 2
        data["large_queue_active_operations_max"] = 8
        return AutoDownloadSettings(**data)

    @staticmethod
    def to_136(obj: AutoDownloadSettings) -> AutoDownloadSettings_136:
        data = obj.to_dict()
        del data["small_queue_active_operations_max"]
        del data["large_queue_active_operations_max"]
        del data["stories_preload"]
        return AutoDownloadSettings_136(**data)

    @staticmethod
    def from_143(obj: AutoDownloadSettings_143) -> AutoDownloadSettings:
        data = obj.to_dict()
        data["small_queue_active_operations_max"] = 2
        data["large_queue_active_operations_max"] = 8
        return AutoDownloadSettings(**data)

    @staticmethod
    def to_143(obj: AutoDownloadSettings) -> AutoDownloadSettings_143:
        data = obj.to_dict()
        del data["stories_preload"]
        del data["large_queue_active_operations_max"]
        del data["small_queue_active_operations_max"]
        return AutoDownloadSettings_143(**data)
