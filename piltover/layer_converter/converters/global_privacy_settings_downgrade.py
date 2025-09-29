from piltover.layer_converter.converters.base import AutoDowngrader
from piltover.tl import GlobalPrivacySettings, GlobalPrivacySettings_133, GlobalPrivacySettings_160, \
    GlobalPrivacySettings_200


class GlobalPrivacySettingsDowngradeTo133(AutoDowngrader):
    BASE_TYPE = GlobalPrivacySettings
    TARGET_TYPE = GlobalPrivacySettings_133
    TARGET_LAYER = 133
    REMOVE_FIELDS = {
        "keep_archived_unmuted", "keep_archived_folders", "hide_read_marks", "new_noncontact_peers_require_premium",
        "display_gifts_button", "noncontact_peers_paid_stars", "disallowed_gifts",
    }


class GlobalPrivacySettingsDowngradeTo160(AutoDowngrader):
    BASE_TYPE = GlobalPrivacySettings
    TARGET_TYPE = GlobalPrivacySettings_160
    TARGET_LAYER = 160
    REMOVE_FIELDS = {
        "hide_read_marks", "new_noncontact_peers_require_premium", "display_gifts_button",
        "noncontact_peers_paid_stars", "disallowed_gifts",
    }


class GlobalPrivacySettingsDowngradeTo200(AutoDowngrader):
    BASE_TYPE = GlobalPrivacySettings
    TARGET_TYPE = GlobalPrivacySettings_200
    TARGET_LAYER = 200
    REMOVE_FIELDS = {"display_gifts_button", "disallowed_gifts"}


class GlobalPrivacySettingsDontDowngrade(AutoDowngrader):
    BASE_TYPE = GlobalPrivacySettings
    TARGET_TYPE = GlobalPrivacySettings
    TARGET_LAYER = 201
    REMOVE_FIELDS = set()
