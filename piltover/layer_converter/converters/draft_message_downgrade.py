from piltover.layer_converter.converters.base import AutoDowngrader
from piltover.tl import DraftMessage, DraftMessage_133, DraftMessage_166


class DraftMessageDowngradeTo133(AutoDowngrader):
    BASE_TYPE = DraftMessage
    TARGET_TYPE = DraftMessage_133
    TARGET_LAYER = 133
    REMOVE_FIELDS = {"invert_media", "reply_to", "media", "effect"}


class DraftMessageDowngradeTo166(AutoDowngrader):
    BASE_TYPE = DraftMessage
    TARGET_TYPE = DraftMessage_166
    TARGET_LAYER = 160
    REMOVE_FIELDS = {"effect"}


class DraftMessageDontDowngrade182(AutoDowngrader):
    BASE_TYPE = DraftMessage
    TARGET_TYPE = DraftMessage
    TARGET_LAYER = 182
    REMOVE_FIELDS = set()


class DraftMessageDontDowngrade(AutoDowngrader):
    BASE_TYPE = DraftMessage
    TARGET_TYPE = DraftMessage
    TARGET_LAYER = 201
    REMOVE_FIELDS = set()
