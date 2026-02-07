from piltover.layer_converter.converters.base import AutoDowngrader
from piltover.tl import PhoneCallDiscarded, PhoneCallDiscarded_133


class PhoneCallDiscardedDowngradeTo133(AutoDowngrader):
    BASE_TYPE = PhoneCallDiscarded
    TARGET_TYPE = PhoneCallDiscarded_133
    TARGET_LAYER = 133
    REMOVE_FIELDS = {"conference_call"}


class PhoneCallDiscardedDontDowngrade196(AutoDowngrader):
    BASE_TYPE = PhoneCallDiscarded
    TARGET_TYPE = PhoneCallDiscarded
    TARGET_LAYER = 196
    REMOVE_FIELDS = set()


class PhoneCallDiscardedDontDowngrade(AutoDowngrader):
    BASE_TYPE = PhoneCallDiscarded
    TARGET_TYPE = PhoneCallDiscarded
    TARGET_LAYER = 201
    REMOVE_FIELDS = set()
