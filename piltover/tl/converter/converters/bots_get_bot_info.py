from piltover.tl.converter import ConverterBase
from piltover.tl.functions.bots import GetBotInfo, GetBotInfo_155


class GetBotInfoConverter(ConverterBase):
    base = GetBotInfo
    old = [GetBotInfo_155]
    layers = [155]

    @staticmethod
    def from_155(obj: GetBotInfo_155) -> GetBotInfo:
        data = obj.to_dict()
        return GetBotInfo(**data)

    @staticmethod
    def to_155(obj: GetBotInfo) -> GetBotInfo_155:
        data = obj.to_dict()
        del data["bot"]
        del data["flags"]
        return GetBotInfo_155(**data)
