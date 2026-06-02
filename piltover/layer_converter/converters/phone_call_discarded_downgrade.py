from piltover.layer_converter.converters.base import AutoDowngrader
from piltover.tl import PhoneCallDiscarded, PhoneCallDiscarded_133


class PhoneCallDiscardedDowngradeTo133(AutoDowngrader):
    BASE_TYPE = PhoneCallDiscarded
    TARGET_TYPE = PhoneCallDiscarded_133
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = {"conference_call"}


class PhoneCallDiscardedDontDowngrade(AutoDowngrader):
    BASE_TYPE = PhoneCallDiscarded
    TARGET_TYPE = PhoneCallDiscarded
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = set()
