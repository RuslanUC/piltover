from piltover.layer_converter.converters.base import AutoDowngrader
from piltover.tl import MessageFwdHeader, MessageFwdHeader_136


class MessageFwdHeaderDowngradeTo136(AutoDowngrader):
    BASE_TYPE = MessageFwdHeader
    TARGET_TYPE = MessageFwdHeader_136
    TARGET_LAYER = 136
    REMOVE_FIELDS = {"saved_out", "saved_from_id", "saved_from_name", "saved_date"}


class MessageFwdHeaderDontDowngrade(AutoDowngrader):
    BASE_TYPE = MessageFwdHeader
    TARGET_TYPE = MessageFwdHeader
    TARGET_LAYER = 177
    REMOVE_FIELDS = set()
