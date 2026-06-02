from piltover.layer_converter.converters.base import AutoDowngrader
from piltover.tl import PhoneCallWaiting, PhoneCallWaiting_133


class PhoneCallWaitingDowngradeTo133(AutoDowngrader):
    BASE_TYPE = PhoneCallWaiting
    TARGET_TYPE = PhoneCallWaiting_133
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = {"conference_call"}


class PhoneCallWaitingDontDowngrade(AutoDowngrader):
    BASE_TYPE = PhoneCallWaiting
    TARGET_TYPE = PhoneCallWaiting
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = set()
