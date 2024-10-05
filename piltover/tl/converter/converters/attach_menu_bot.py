from piltover.tl.converter import ConverterBase
from piltover.tl.types import AttachMenuBot, AttachMenuBot_140, AttachMenuBot_143


class AttachMenuBotConverter(ConverterBase):
    base = AttachMenuBot
    old = [AttachMenuBot_140, AttachMenuBot_143]
    layers = [140, 143]

    @staticmethod
    def from_140(obj: AttachMenuBot_140) -> AttachMenuBot:
        data = obj.to_dict()
        return AttachMenuBot(**data)

    @staticmethod
    def to_140(obj: AttachMenuBot) -> AttachMenuBot_140:
        data = obj.to_dict()
        del data["show_in_attach_menu"]
        del data["peer_types"]
        del data["has_settings"]
        del data["request_write_access"]
        del data["show_in_side_menu"]
        del data["side_menu_disclaimer_needed"]
        return AttachMenuBot_140(**data)

    @staticmethod
    def from_143(obj: AttachMenuBot_143) -> AttachMenuBot:
        data = obj.to_dict()
        return AttachMenuBot(**data)

    @staticmethod
    def to_143(obj: AttachMenuBot) -> AttachMenuBot_143:
        data = obj.to_dict()
        del data["show_in_attach_menu"]
        del data["request_write_access"]
        del data["show_in_side_menu"]
        del data["side_menu_disclaimer_needed"]
        if data["peer_types"] is None:
            data["peer_types"] = []
        return AttachMenuBot_143(**data)
