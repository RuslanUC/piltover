from piltover.layer_converter.converters.base import AutoDowngrader
from piltover.tl import MessageReplyHeader, MessageReplyHeader_136, MessageReplyHeader_166


class MessageReplyHeaderDowngradeTo136(AutoDowngrader):
    BASE_TYPE = MessageReplyHeader
    TARGET_LAYER = 136
    TARGET_TYPE = MessageReplyHeader_136
    REMOVE_FIELDS = {
        "forum_topic", "quote", "reply_from", "reply_media", "quote_text", "quote_entities", "quote_offset"
    }


class MessageReplyHeaderDowngradeTo166(AutoDowngrader):
    BASE_TYPE = MessageReplyHeader
    TARGET_LAYER = 166
    TARGET_TYPE = MessageReplyHeader_166
    REMOVE_FIELDS = {
        "quote_offset"
    }


class MessageReplyHeaderDontDowngrade(AutoDowngrader):
    BASE_TYPE = MessageReplyHeader
    TARGET_LAYER = 177
    TARGET_TYPE = MessageReplyHeader
    REMOVE_FIELDS = set()
