from piltover.layer_converter.converters.base import AutoDowngrader
from piltover.tl import BotInfo, BotInfo_133, BotInfo_193, BotInfo_186, BotInfo_143, BotInfo_140


class BotInfoDowngradeTo133(AutoDowngrader):
    BASE_TYPE = BotInfo
    TARGET_TYPE = BotInfo_133
    TARGET_LAYER = 133
    REMOVE_FIELDS = {
        "description_photo", "description_document", "menu_button", "has_preview_medias", "privacy_policy_url",
        "app_settings", "verifier_settings",
    }


class BotInfoDowngradeTo140(AutoDowngrader):
    BASE_TYPE = BotInfo
    TARGET_TYPE = BotInfo_140
    TARGET_LAYER = 140
    REMOVE_FIELDS = {
        "description_photo", "description_document", "has_preview_medias", "privacy_policy_url", "app_settings",
        "verifier_settings",
    }


class BotInfoDowngradeTo143(AutoDowngrader):
    BASE_TYPE = BotInfo
    TARGET_TYPE = BotInfo_143
    TARGET_LAYER = 143
    REMOVE_FIELDS = {"has_preview_medias", "privacy_policy_url", "app_settings", "verifier_settings"}


class BotInfoDowngradeTo186(AutoDowngrader):
    BASE_TYPE = BotInfo
    TARGET_TYPE = BotInfo_186
    TARGET_LAYER = 186
    REMOVE_FIELDS = {"app_settings", "verifier_settings"}


class BotInfoDowngradeTo193(AutoDowngrader):
    BASE_TYPE = BotInfo
    TARGET_TYPE = BotInfo_193
    TARGET_LAYER = 193
    REMOVE_FIELDS = {"verifier_settings"}


class BotInfoDontDowngrade(AutoDowngrader):
    BASE_TYPE = BotInfo
    TARGET_TYPE = BotInfo
    TARGET_LAYER = 201
    REMOVE_FIELDS = set()
