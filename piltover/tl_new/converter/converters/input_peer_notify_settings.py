from piltover.tl_new.converter import ConverterBase
from piltover.tl_new.types import InputPeerNotifySettings, InputPeerNotifySettings_136, InputPeerNotifySettings_140


class InputPeerNotifySettingsConverter(ConverterBase):
    base = InputPeerNotifySettings
    old = [InputPeerNotifySettings_136, InputPeerNotifySettings_140]
    layers = [136, 140]

    @staticmethod
    def from_136(obj: InputPeerNotifySettings_136) -> InputPeerNotifySettings:
        data = obj.to_dict()
        data["sound"] = None
        return InputPeerNotifySettings(**data)

    @staticmethod
    def to_136(obj: InputPeerNotifySettings) -> InputPeerNotifySettings_136:
        data = obj.to_dict()
        del data["stories_muted"]
        del data["stories_hide_sender"]
        del data["stories_sound"]
        data["sound"] = None
        return InputPeerNotifySettings_136(**data)

    @staticmethod
    def from_140(obj: InputPeerNotifySettings_140) -> InputPeerNotifySettings:
        data = obj.to_dict()
        return InputPeerNotifySettings(**data)

    @staticmethod
    def to_140(obj: InputPeerNotifySettings) -> InputPeerNotifySettings_140:
        data = obj.to_dict()
        del data["stories_muted"]
        del data["stories_hide_sender"]
        del data["stories_sound"]
        return InputPeerNotifySettings_140(**data)
