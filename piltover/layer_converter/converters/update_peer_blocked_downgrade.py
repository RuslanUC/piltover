from piltover.layer_converter.converters.base import AutoDowngrader
from piltover.tl import UpdatePeerBlocked, UpdatePeerBlocked_133


class UpdatePeerBlockedDowngradeTo133(AutoDowngrader):
    BASE_TYPE = UpdatePeerBlocked
    TARGET_TYPE = UpdatePeerBlocked_133
    TARGET_LAYER = 133
    REMOVE_FIELDS = {"blocked_my_stories_from"}


class UpdatePeerBlockedDontDowngrade(AutoDowngrader):
    BASE_TYPE = UpdatePeerBlocked
    TARGET_TYPE = UpdatePeerBlocked
    TARGET_LAYER = 201
    REMOVE_FIELDS = set()
