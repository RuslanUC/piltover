from piltover.layer_converter.converters.base import AutoDowngrader
from piltover.tl import PhoneCallAccepted, PhoneCallAccepted_133


class PhoneCallAcceptedDowngradeTo133(AutoDowngrader):
    BASE_TYPE = PhoneCallAccepted
    TARGET_TYPE = PhoneCallAccepted_133
    TARGET_LAYER = 133
    REMOVE_FIELDS = {"conference_call"}


class PhoneCallAcceptedDontDowngrade196(AutoDowngrader):
    BASE_TYPE = PhoneCallAccepted
    TARGET_TYPE = PhoneCallAccepted
    TARGET_LAYER = 196
    REMOVE_FIELDS = set()


class PhoneCallAcceptedDontDowngrade(AutoDowngrader):
    BASE_TYPE = PhoneCallAccepted
    TARGET_TYPE = PhoneCallAccepted
    TARGET_LAYER = 201
    REMOVE_FIELDS = set()
