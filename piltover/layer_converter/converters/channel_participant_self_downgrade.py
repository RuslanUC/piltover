from piltover.layer_converter.converters.base import AutoDowngrader
from piltover.tl import ChannelParticipantSelf, ChannelParticipantSelf_136


class ChannelParticipantSelfDowngradeTo136(AutoDowngrader):
    BASE_TYPE = ChannelParticipantSelf
    TARGET_LAYER = 136
    TARGET_TYPE = ChannelParticipantSelf_136
    REMOVE_FIELDS = {"subscription_until_date"}


class ChannelParticipantSelfDontDowngrade(AutoDowngrader):
    BASE_TYPE = ChannelParticipantSelf
    TARGET_LAYER = 201
    TARGET_TYPE = ChannelParticipantSelf
    REMOVE_FIELDS = set()
