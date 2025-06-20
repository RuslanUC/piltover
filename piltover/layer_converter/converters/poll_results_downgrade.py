from piltover.layer_converter.converters.base import AutoDowngrader
from piltover.tl import PollResults, PollResults_136


class PollResultsDowngradeTo136(AutoDowngrader):
    BASE_TYPE = PollResults
    TARGET_LAYER = 136
    TARGET_TYPE = PollResults_136
    REMOVE_FIELDS = set()


class PollResultsDontDowngrade(AutoDowngrader):
    BASE_TYPE = PollResults
    TARGET_LAYER = 201
    TARGET_TYPE = PollResults
    REMOVE_FIELDS = set()
