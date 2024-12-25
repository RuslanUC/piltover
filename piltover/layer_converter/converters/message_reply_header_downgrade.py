from copy import copy

from piltover.layer_converter.converters.base import BaseDowngrader
from piltover.tl import PeerSettings, PeerSettings_136, MessageReplyHeader, MessageReplyHeader_136, \
    MessageReplyHeader_166


class MessageReplyHeaderDowngradeTo136(BaseDowngrader):
    BASE_TYPE = MessageReplyHeader
    TARGET_LAYER = 136

    @classmethod
    def downgrade(cls, from_obj: MessageReplyHeader) -> MessageReplyHeader_136:
        kwargs = from_obj.to_dict()
        del kwargs["forum_topic"]
        del kwargs["quote"]
        del kwargs["reply_from"]
        del kwargs["reply_media"]
        del kwargs["quote_text"]
        del kwargs["quote_entities"]
        del kwargs["quote_offset"]

        return MessageReplyHeader_136(**kwargs)


class MessageReplyHeaderDowngradeTo166(BaseDowngrader):
    BASE_TYPE = MessageReplyHeader
    TARGET_LAYER = 166

    @classmethod
    def downgrade(cls, from_obj: MessageReplyHeader) -> MessageReplyHeader_166:
        kwargs = from_obj.to_dict()
        del kwargs["quote_offset"]

        return MessageReplyHeader_166(**kwargs)


class MessageReplyHeaderDontDowngrade(BaseDowngrader):
    BASE_TYPE = MessageReplyHeader
    TARGET_LAYER = 177

    @classmethod
    def downgrade(cls, from_obj: MessageReplyHeader) -> MessageReplyHeader:
        return copy(from_obj)
