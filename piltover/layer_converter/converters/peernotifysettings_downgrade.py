from piltover.layer_converter.converters.base import AutoDowngrader
from piltover.tl import PeerNotifySettings, PeerNotifySettings_133, PeerNotifySettings_140


class PeerNotifySettingsDowngradeTo133(AutoDowngrader):
    BASE_TYPE = PeerNotifySettings
    TARGET_TYPE = PeerNotifySettings_133
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = {
        "ios_sound", "android_sound", "other_sound", "stories_muted", "stories_hide_sender", "stories_ios_sound",
        "stories_android_sound", "stories_other_sound",
    }


class PeerNotifySettingsDowngradeTo140(AutoDowngrader):
    BASE_TYPE = PeerNotifySettings
    TARGET_TYPE = PeerNotifySettings_140
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = {
        "stories_muted", "stories_hide_sender", "stories_ios_sound", "stories_android_sound", "stories_other_sound",
    }


class PeerNotifySettingsDontDowngrade(AutoDowngrader):
    BASE_TYPE = PeerNotifySettings
    TARGET_TYPE = PeerNotifySettings
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = set()
