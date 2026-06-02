from piltover.layer_converter.converters.base import AutoDowngrader
from piltover.tl.types.help import PeerColorOption, PeerColorOption_168, PeerColorOption_167


class PeerColorOptionDowngradeTo167(AutoDowngrader):
    BASE_TYPE = PeerColorOption
    TARGET_TYPE = PeerColorOption_167
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = {"channel_min_level", "group_min_level"}


class PeerColorOptionDowngradeTo168(AutoDowngrader):
    BASE_TYPE = PeerColorOption
    TARGET_TYPE = PeerColorOption_168
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = {"group_min_level"}


class PeerColorOptionDontDowngrade(AutoDowngrader):
    BASE_TYPE = PeerColorOption
    TARGET_TYPE = PeerColorOption
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = set()
