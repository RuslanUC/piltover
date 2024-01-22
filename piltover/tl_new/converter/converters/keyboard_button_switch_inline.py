from piltover.tl_new.types import KeyboardButtonSwitchInline, KeyboardButtonSwitchInline_136
from piltover.tl_new.converter import ConverterBase


class KeyboardButtonSwitchInlineConverter(ConverterBase):
    base = KeyboardButtonSwitchInline
    old = [KeyboardButtonSwitchInline_136]
    layers = [136]

    @staticmethod
    def from_136(obj: KeyboardButtonSwitchInline_136) -> KeyboardButtonSwitchInline:
        data = obj.to_dict()
        return KeyboardButtonSwitchInline(**data)

    @staticmethod
    def to_136(obj: KeyboardButtonSwitchInline) -> KeyboardButtonSwitchInline_136:
        data = obj.to_dict()
        del data["peer_types"]
        return KeyboardButtonSwitchInline_136(**data)

