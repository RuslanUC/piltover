from piltover.tl.converter import ConverterBase
from piltover.tl.types import Config, Config_136, Config_145


class ConfigConverter(ConverterBase):
    base = Config
    old = [Config_136, Config_145]
    layers = [136, 145]

    @staticmethod
    def from_136(obj: Config_136) -> Config:
        data = obj.to_dict()
        del data["saved_gifs_limit"]
        del data["ignore_phone_entities"]
        del data["stickers_faved_limit"]
        del data["pfs_enabled"]
        del data["pinned_infolder_count_max"]
        del data["phonecalls_enabled"]
        del data["pinned_dialogs_count_max"]
        return Config(**data)

    @staticmethod
    def to_136(obj: Config) -> Config_136:
        data = obj.to_dict()
        del data["reactions_default"]
        del data["autologin_token"]
        data["saved_gifs_limit"] = 20
        data["stickers_faved_limit"] = 20
        data["pinned_infolder_count_max"] = 5
        data["pinned_dialogs_count_max"] = 5
        return Config_136(**data)

    @staticmethod
    def from_145(obj: Config_145) -> Config:
        data = obj.to_dict()
        del data["saved_gifs_limit"]
        del data["ignore_phone_entities"]
        del data["stickers_faved_limit"]
        del data["pfs_enabled"]
        del data["pinned_infolder_count_max"]
        del data["phonecalls_enabled"]
        del data["pinned_dialogs_count_max"]
        return Config(**data)

    @staticmethod
    def to_145(obj: Config) -> Config_145:
        data = obj.to_dict()
        del data["autologin_token"]
        data["saved_gifs_limit"] = 20
        data["stickers_faved_limit"] = 20
        data["pinned_infolder_count_max"] = 5
        data["pinned_dialogs_count_max"] = 5
        return Config_145(**data)
