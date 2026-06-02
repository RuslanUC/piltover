from piltover.layer_converter.converters.base import AutoDowngrader
from piltover.tl import UpdatePeerBlocked, UpdatePeerBlocked_133


class UpdatePeerBlockedDowngradeTo133(AutoDowngrader):
    BASE_TYPE = UpdatePeerBlocked
    TARGET_TYPE = UpdatePeerBlocked_133
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = {"blocked_my_stories_from"}


class UpdatePeerBlockedDontDowngrade(AutoDowngrader):
    BASE_TYPE = UpdatePeerBlocked
    TARGET_TYPE = UpdatePeerBlocked
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = set()
