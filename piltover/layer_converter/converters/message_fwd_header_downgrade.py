from piltover.layer_converter.converters.base import AutoDowngrader
from piltover.tl import MessageFwdHeader, MessageFwdHeader_133


class MessageFwdHeaderDowngradeTo133(AutoDowngrader):
    BASE_TYPE = MessageFwdHeader
    TARGET_TYPE = MessageFwdHeader_133
    TARGET_LAYER = 133
    REMOVE_FIELDS = {"saved_out", "saved_from_id", "saved_from_name", "saved_date"}


class MessageFwdHeaderDontDowngrade(AutoDowngrader):
    BASE_TYPE = MessageFwdHeader
    TARGET_TYPE = MessageFwdHeader
    TARGET_LAYER = 201
    REMOVE_FIELDS = set()
