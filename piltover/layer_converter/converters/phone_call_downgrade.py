from piltover.layer_converter.converters.base import AutoDowngrader
from piltover.tl import PhoneCall, PhoneCall_133


class PhoneCallDowngradeTo133(AutoDowngrader):
    BASE_TYPE = PhoneCall
    TARGET_TYPE = PhoneCall_133
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = {"custom_parameters", "conference_call"}


class PhoneCallDontDowngrade(AutoDowngrader):
    BASE_TYPE = PhoneCall
    TARGET_TYPE = PhoneCall
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = set()
