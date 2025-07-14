from piltover.layer_converter.converters.base import AutoDowngrader
from piltover.tl import UpdatePeerBlocked, UpdatePeerBlocked_136


class UpdatePeerBlockedDowngradeTo136(AutoDowngrader):
    BASE_TYPE = UpdatePeerBlocked
    TARGET_TYPE = UpdatePeerBlocked_136
    TARGET_LAYER = 136
    REMOVE_FIELDS = {"blocked_my_stories_from"}


class UpdatePeerBlockedDontDowngrade(AutoDowngrader):
    BASE_TYPE = UpdatePeerBlocked
    TARGET_TYPE = UpdatePeerBlocked
    TARGET_LAYER = 201
    REMOVE_FIELDS = set()
