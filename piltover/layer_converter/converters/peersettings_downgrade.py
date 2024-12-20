from copy import copy

from piltover.layer_converter.converters.base import BaseDowngrader
from piltover.tl import PeerSettings, PeerSettings_136


class PeerSettingsDowngradeTo136(BaseDowngrader):
    BASE_TYPE = PeerSettings
    TARGET_LAYER = 136

    @classmethod
    def downgrade(cls, from_obj: PeerSettings) -> PeerSettings_136:
        kwargs = from_obj.to_dict()
        del kwargs["business_bot_paused"]
        del kwargs["business_bot_can_reply"]
        del kwargs["business_bot_id"]
        del kwargs["business_bot_manage_url"]

        return PeerSettings_136(**kwargs)


class PeerSettingsDontDowngrade(BaseDowngrader):
    BASE_TYPE = PeerSettings
    TARGET_LAYER = 177

    @classmethod
    def downgrade(cls, from_obj: PeerSettings) -> PeerSettings:
        return copy(from_obj)
