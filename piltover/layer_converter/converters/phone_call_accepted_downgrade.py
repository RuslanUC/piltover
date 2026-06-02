from piltover.layer_converter.converters.base import AutoDowngrader
from piltover.tl import PhoneCallAccepted, PhoneCallAccepted_133


class PhoneCallAcceptedDowngradeTo133(AutoDowngrader):
    BASE_TYPE = PhoneCallAccepted
    TARGET_TYPE = PhoneCallAccepted_133
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = {"conference_call"}


class PhoneCallAcceptedDontDowngrade(AutoDowngrader):
    BASE_TYPE = PhoneCallAccepted
    TARGET_TYPE = PhoneCallAccepted
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = set()
