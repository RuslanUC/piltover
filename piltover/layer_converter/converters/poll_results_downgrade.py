from piltover.layer_converter.converters.base import AutoDowngrader
from piltover.tl import PollResults, PollResults_133


class PollResultsDowngradeTo133(AutoDowngrader):
    BASE_TYPE = PollResults
    TARGET_LAYER = 133
    TARGET_TYPE = PollResults_133
    REMOVE_FIELDS = set()


class PollResultsDontDowngrade(AutoDowngrader):
    BASE_TYPE = PollResults
    TARGET_LAYER = 201
    TARGET_TYPE = PollResults
    REMOVE_FIELDS = set()
