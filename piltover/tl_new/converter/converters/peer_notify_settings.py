from piltover.tl_new.types import PeerNotifySettings, PeerNotifySettings_136, PeerNotifySettings_140
from piltover.tl_new.converter import ConverterBase


class PeerNotifySettingsConverter(ConverterBase):
    base = PeerNotifySettings
    old = [PeerNotifySettings_136, PeerNotifySettings_140]
    layers = [136, 140]

    @staticmethod
    def from_136(obj: PeerNotifySettings_136) -> PeerNotifySettings:
        data = obj.to_dict()
        del data["sound"]
        return PeerNotifySettings(**data)

    @staticmethod
    def to_136(obj: PeerNotifySettings) -> PeerNotifySettings_136:
        data = obj.to_dict()
        del data["stories_ios_sound"]
        del data["android_sound"]
        del data["ios_sound"]
        del data["stories_android_sound"]
        del data["stories_muted"]
        del data["stories_other_sound"]
        del data["other_sound"]
        del data["stories_hide_sender"]
        return PeerNotifySettings_136(**data)

    @staticmethod
    def from_140(obj: PeerNotifySettings_140) -> PeerNotifySettings:
        data = obj.to_dict()
        return PeerNotifySettings(**data)

    @staticmethod
    def to_140(obj: PeerNotifySettings) -> PeerNotifySettings_140:
        data = obj.to_dict()
        del data["stories_ios_sound"]
        del data["stories_android_sound"]
        del data["stories_other_sound"]
        del data["stories_muted"]
        del data["stories_hide_sender"]
        return PeerNotifySettings_140(**data)

