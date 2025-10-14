from piltover.layer_converter.converters.base import AutoDowngrader
from piltover.tl.types.help import PeerColorOption, PeerColorOption_168, PeerColorOption_167


class PeerColorOptionDowngradeTo167(AutoDowngrader):
    BASE_TYPE = PeerColorOption
    TARGET_LAYER = 167
    TARGET_TYPE = PeerColorOption_167
    REMOVE_FIELDS = {"channel_min_level", "group_min_level"}


class PeerColorOptionDowngradeTo168(AutoDowngrader):
    BASE_TYPE = PeerColorOption
    TARGET_LAYER = 168
    TARGET_TYPE = PeerColorOption_168
    REMOVE_FIELDS = {"group_min_level"}


class PeerColorOptionDontDowngrade(AutoDowngrader):
    BASE_TYPE = PeerColorOption
    TARGET_LAYER = 201
    TARGET_TYPE = PeerColorOption
    REMOVE_FIELDS = set()
