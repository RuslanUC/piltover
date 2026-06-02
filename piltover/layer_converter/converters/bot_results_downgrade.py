from piltover.layer_converter.converters.base import AutoDowngrader
from piltover.tl.types.messages import BotResults, BotResults_133


class BotResultsDowngradeTo133(AutoDowngrader):
    BASE_TYPE = BotResults
    TARGET_TYPE = BotResults_133
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = {"switch_webview"}


class BotResultsDontDowngrade(AutoDowngrader):
    BASE_TYPE = BotResults
    TARGET_TYPE = BotResults
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = set()
