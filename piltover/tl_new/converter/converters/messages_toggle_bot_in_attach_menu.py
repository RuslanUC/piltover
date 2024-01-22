from piltover.tl_new.functions.messages import ToggleBotInAttachMenu, ToggleBotInAttachMenu_140
from piltover.tl_new.converter import ConverterBase


class ToggleBotInAttachMenuConverter(ConverterBase):
    base = ToggleBotInAttachMenu
    old = [ToggleBotInAttachMenu_140]
    layers = [140]

    @staticmethod
    def from_140(obj: ToggleBotInAttachMenu_140) -> ToggleBotInAttachMenu:
        data = obj.to_dict()
        return ToggleBotInAttachMenu(**data)

    @staticmethod
    def to_140(obj: ToggleBotInAttachMenu) -> ToggleBotInAttachMenu_140:
        data = obj.to_dict()
        del data["write_allowed"]
        del data["flags"]
        return ToggleBotInAttachMenu_140(**data)

