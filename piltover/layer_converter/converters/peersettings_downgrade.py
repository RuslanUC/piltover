from piltover.layer_converter.converters.base import AutoDowngrader
from piltover.tl import PeerSettings, PeerSettings_136


class PeerSettingsDowngradeTo136(AutoDowngrader):
    BASE_TYPE = PeerSettings
    TARGET_LAYER = 136
    TARGET_TYPE = PeerSettings_136
    REMOVE_FIELDS = {
        "business_bot_paused", "business_bot_can_reply", "business_bot_id", "business_bot_manage_url",
    }


class PeerSettingsDontDowngrade(AutoDowngrader):
    BASE_TYPE = PeerSettings
    TARGET_LAYER = 177
    TARGET_TYPE = PeerSettings
    REMOVE_FIELDS = set()
