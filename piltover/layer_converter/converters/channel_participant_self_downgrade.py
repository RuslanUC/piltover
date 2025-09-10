from piltover.layer_converter.converters.base import AutoDowngrader
from piltover.tl import ChannelParticipantSelf, ChannelParticipantSelf_134, ChannelParticipantSelf_133


class ChannelParticipantSelfDowngradeTo133(AutoDowngrader):
    BASE_TYPE = ChannelParticipantSelf
    TARGET_LAYER = 133
    TARGET_TYPE = ChannelParticipantSelf_133
    REMOVE_FIELDS = {"subscription_until_date", "via_request"}


class ChannelParticipantSelfDowngradeTo134(AutoDowngrader):
    BASE_TYPE = ChannelParticipantSelf
    TARGET_LAYER = 134
    TARGET_TYPE = ChannelParticipantSelf_134
    REMOVE_FIELDS = {"subscription_until_date"}


class ChannelParticipantSelfDontDowngrade(AutoDowngrader):
    BASE_TYPE = ChannelParticipantSelf
    TARGET_LAYER = 201
    TARGET_TYPE = ChannelParticipantSelf
    REMOVE_FIELDS = set()
