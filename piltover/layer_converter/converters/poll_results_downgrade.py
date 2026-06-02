from piltover.layer_converter.converters.base import AutoDowngrader
from piltover.tl import PollResults, PollResults_133


class PollResultsDowngradeTo133(AutoDowngrader):
    BASE_TYPE = PollResults
    TARGET_TYPE = PollResults_133
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = set()


class PollResultsDontDowngrade(AutoDowngrader):
    BASE_TYPE = PollResults
    TARGET_TYPE = PollResults
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = set()
