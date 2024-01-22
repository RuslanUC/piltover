from piltover.tl_new.functions.help import GetAppConfig, GetAppConfig_136
from piltover.tl_new.converter import ConverterBase


class GetAppConfigConverter(ConverterBase):
    base = GetAppConfig
    old = [GetAppConfig_136]
    layers = [136]

    @staticmethod
    def from_136(obj: GetAppConfig_136) -> GetAppConfig:
        data = obj.to_dict()
        data["hash"] = 0
        return GetAppConfig(**data)

    @staticmethod
    def to_136(obj: GetAppConfig) -> GetAppConfig_136:
        data = obj.to_dict()
        del data["hash"]
        return GetAppConfig_136(**data)

