from piltover.layer_converter.converters.base import AutoDowngrader
from piltover.tl.types.messages import BotResults, BotResults_133


class BotResultsDowngradeTo133(AutoDowngrader):
    BASE_TYPE = BotResults
    TARGET_TYPE = BotResults_133
    TARGET_LAYER = 133
    REMOVE_FIELDS = {"switch_webview"}


class BotResultsDontDowngrade155(AutoDowngrader):
    BASE_TYPE = BotResults
    TARGET_TYPE = BotResults
    TARGET_LAYER = 155
    REMOVE_FIELDS = set()


class BotResultsDontDowngrade(AutoDowngrader):
    BASE_TYPE = BotResults
    TARGET_TYPE = BotResults
    TARGET_LAYER = 201
    REMOVE_FIELDS = set()
