from piltover.layer_converter.converters.base import AutoDowngrader
from piltover.tl import PeerSettings, PeerSettings_133, PeerSettings_135, PeerSettings_177


class PeerSettingsDowngradeTo133(AutoDowngrader):
    BASE_TYPE = PeerSettings
    TARGET_TYPE = PeerSettings_133
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = {
        "business_bot_paused", "business_bot_can_reply", "business_bot_id", "business_bot_manage_url",
        "charge_paid_message_stars", "registration_month", "phone_country", "name_change_date", "photo_change_date",
        "request_chat_broadcast", "request_chat_title", "request_chat_date",
    }


class PeerSettingsDowngradeTo135(AutoDowngrader):
    BASE_TYPE = PeerSettings
    TARGET_TYPE = PeerSettings_135
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = {
        "business_bot_paused", "business_bot_can_reply", "business_bot_id", "business_bot_manage_url",
        "charge_paid_message_stars", "registration_month", "phone_country", "name_change_date", "photo_change_date",
    }


class PeerSettingsDowngradeTo177(AutoDowngrader):
    BASE_TYPE = PeerSettings
    TARGET_TYPE = PeerSettings_177
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = {
        "charge_paid_message_stars", "registration_month", "phone_country", "name_change_date", "photo_change_date",
    }


class PeerSettingsDontDowngrade(AutoDowngrader):
    BASE_TYPE = PeerSettings
    TARGET_TYPE = PeerSettings
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = set()
