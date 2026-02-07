from piltover.layer_converter.converters.base import AutoDowngrader
from piltover.tl import PhoneCallWaiting, PhoneCallWaiting_133


class PhoneCallWaitingDowngradeTo133(AutoDowngrader):
    BASE_TYPE = PhoneCallWaiting
    TARGET_TYPE = PhoneCallWaiting_133
    TARGET_LAYER = 133
    REMOVE_FIELDS = {"conference_call"}


class PhoneCallWaitingDontDowngrade196(AutoDowngrader):
    BASE_TYPE = PhoneCallWaiting
    TARGET_TYPE = PhoneCallWaiting
    TARGET_LAYER = 196
    REMOVE_FIELDS = set()


class PhoneCallWaitingDontDowngrade(AutoDowngrader):
    BASE_TYPE = PhoneCallWaiting
    TARGET_TYPE = PhoneCallWaiting
    TARGET_LAYER = 201
    REMOVE_FIELDS = set()
