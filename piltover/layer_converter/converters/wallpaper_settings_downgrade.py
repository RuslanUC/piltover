from piltover.layer_converter.converters.base import AutoDowngrader
from piltover.tl import WallPaperSettings, WallPaperSettings_133


class WallPaperSettingsDowngradeTo133(AutoDowngrader):
    BASE_TYPE = WallPaperSettings
    TARGET_TYPE = WallPaperSettings_133
    TARGET_LAYER = 133
    REMOVE_FIELDS = {"emoticon"}


class WallPaperSettingsDontDowngrade(AutoDowngrader):
    BASE_TYPE = WallPaperSettings
    TARGET_TYPE = WallPaperSettings
    TARGET_LAYER = 201
    REMOVE_FIELDS = set()
