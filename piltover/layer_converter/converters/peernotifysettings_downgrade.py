from copy import copy

from piltover.layer_converter.converters.base import BaseDowngrader
from piltover.tl import PeerNotifySettings, PeerNotifySettings_136, PeerNotifySettings_140


class PeerNotifySettingsDowngradeTo136(BaseDowngrader):
    BASE_TYPE = PeerNotifySettings
    TARGET_LAYER = 136

    @classmethod
    def downgrade(cls, from_obj: PeerNotifySettings) -> PeerNotifySettings_136:
        kwargs = from_obj.to_dict()
        del kwargs["ios_sound"]
        del kwargs["android_sound"]
        del kwargs["other_sound"]
        del kwargs["stories_muted"]
        del kwargs["stories_hide_sender"]
        del kwargs["stories_ios_sound"]
        del kwargs["stories_android_sound"]
        del kwargs["stories_other_sound"]

        return PeerNotifySettings_136(**kwargs)


class PeerNotifySettingsDowngradeTo140(BaseDowngrader):
    BASE_TYPE = PeerNotifySettings
    TARGET_LAYER = 140

    @classmethod
    def downgrade(cls, from_obj: PeerNotifySettings) -> PeerNotifySettings_140:
        kwargs = from_obj.to_dict()
        del kwargs["stories_muted"]
        del kwargs["stories_hide_sender"]
        del kwargs["stories_ios_sound"]
        del kwargs["stories_android_sound"]
        del kwargs["stories_other_sound"]

        return PeerNotifySettings_140(**kwargs)


class PeerNotifySettingsDontDowngrade(BaseDowngrader):
    BASE_TYPE = PeerNotifySettings
    TARGET_LAYER = 177

    @classmethod
    def downgrade(cls, from_obj: PeerNotifySettings) -> PeerNotifySettings:
        return copy(from_obj)
