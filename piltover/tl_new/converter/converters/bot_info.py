from piltover.tl_new import BotMenuButton
from piltover.tl_new.converter import ConverterBase
from piltover.tl_new.types import BotInfo, BotInfo_136, BotInfo_140


class BotInfoConverter(ConverterBase):
    base = BotInfo
    old = [BotInfo_136, BotInfo_140]
    layers = [136, 140]

    @staticmethod
    def from_136(obj: BotInfo_136) -> BotInfo:
        data = obj.to_dict()
        return BotInfo(**data)

    @staticmethod
    def to_136(obj: BotInfo) -> BotInfo_136:
        data = obj.to_dict()
        del data["description_photo"]
        del data["flags"]
        del data["menu_button"]
        del data["description_document"]
        if data["user_id"] is None:
            data["user_id"] = 0
        if data["description"] is None:
            data["description"] = ""
        if data["commands"] is None:
            data["commands"] = []
        return BotInfo_136(**data)

    @staticmethod
    def from_140(obj: BotInfo_140) -> BotInfo:
        data = obj.to_dict()
        return BotInfo(**data)

    @staticmethod
    def to_140(obj: BotInfo) -> BotInfo_140:
        data = obj.to_dict()
        del data["description_photo"]
        del data["flags"]
        del data["description_document"]
        if data["menu_button"] is None:
            data["menu_button"] = BotMenuButton(text="", url="")
        if data["user_id"] is None:
            data["user_id"] = 0
        if data["description"] is None:
            data["description"] = ""
        if data["commands"] is None:
            data["commands"] = []
        return BotInfo_140(**data)
