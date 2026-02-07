from piltover.layer_converter.converters.base import AutoDowngrader
from piltover.tl import PhoneCall, PhoneCall_133


class PhoneCallDowngradeTo133(AutoDowngrader):
    BASE_TYPE = PhoneCall
    TARGET_TYPE = PhoneCall_133
    TARGET_LAYER = 133
    REMOVE_FIELDS = {"custom_parameters", "conference_call"}


class PhoneCallDontDowngrade196(AutoDowngrader):
    BASE_TYPE = PhoneCall
    TARGET_TYPE = PhoneCall
    TARGET_LAYER = 196
    REMOVE_FIELDS = set()


class PhoneCallDontDowngrade(AutoDowngrader):
    BASE_TYPE = PhoneCall
    TARGET_TYPE = PhoneCall
    TARGET_LAYER = 201
    REMOVE_FIELDS = set()
