from piltover.layer_converter.converters.base import AutoDowngrader
from piltover.tl import PhoneCallRequested, PhoneCallRequested_133


class PhoneCallRequestedDowngradeTo133(AutoDowngrader):
    BASE_TYPE = PhoneCallRequested
    TARGET_TYPE = PhoneCallRequested_133
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = {"conference_call"}


class PhoneCallRequestedDontDowngrade(AutoDowngrader):
    BASE_TYPE = PhoneCallRequested
    TARGET_TYPE = PhoneCallRequested
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = set()
