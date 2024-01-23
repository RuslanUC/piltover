from piltover.tl_new.converter import ConverterBase
from piltover.tl_new.functions.bots import SetBotInfo, SetBotInfo_155


class SetBotInfoConverter(ConverterBase):
    base = SetBotInfo
    old = [SetBotInfo_155]
    layers = [155]

    @staticmethod
    def from_155(obj: SetBotInfo_155) -> SetBotInfo:
        data = obj.to_dict()
        return SetBotInfo(**data)

    @staticmethod
    def to_155(obj: SetBotInfo) -> SetBotInfo_155:
        data = obj.to_dict()
        del data["name"]
        del data["bot"]
        return SetBotInfo_155(**data)
