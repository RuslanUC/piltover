from piltover.layer_converter.converters.base import AutoDowngrader
from piltover.tl import MessageReplyHeader, MessageReplyHeader_133, MessageReplyHeader_166


class MessageReplyHeaderDowngradeTo133(AutoDowngrader):
    BASE_TYPE = MessageReplyHeader
    TARGET_TYPE = MessageReplyHeader_133
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = {
        "forum_topic", "quote", "reply_from", "reply_media", "quote_text", "quote_entities", "quote_offset"
    }


class MessageReplyHeaderDowngradeTo166(AutoDowngrader):
    BASE_TYPE = MessageReplyHeader
    TARGET_TYPE = MessageReplyHeader_166
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = {
        "quote_offset"
    }


class MessageReplyHeaderDontDowngrade(AutoDowngrader):
    BASE_TYPE = MessageReplyHeader
    TARGET_TYPE = MessageReplyHeader
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = set()
