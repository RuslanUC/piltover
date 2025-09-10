from piltover.layer_converter.converters.base import AutoDowngrader
from piltover.tl import ChannelParticipant, ChannelParticipant_133


class ChannelParticipantDowngradeTo133(AutoDowngrader):
    BASE_TYPE = ChannelParticipant
    TARGET_LAYER = 133
    TARGET_TYPE = ChannelParticipant_133
    REMOVE_FIELDS = {"subscription_until_date"}


class ChannelParticipantDontDowngrade(AutoDowngrader):
    BASE_TYPE = ChannelParticipant
    TARGET_LAYER = 201
    TARGET_TYPE = ChannelParticipant
    REMOVE_FIELDS = set()
