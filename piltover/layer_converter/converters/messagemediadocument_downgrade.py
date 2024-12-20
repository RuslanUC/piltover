from copy import copy

from piltover.layer_converter.converters.base import BaseDowngrader
from piltover.tl import MessageMediaDocument, MessageMediaDocument_136


class MessageMediaDocumentDowngradeTo136(BaseDowngrader):
    BASE_TYPE = MessageMediaDocument
    TARGET_LAYER = 136

    @classmethod
    def downgrade(cls, from_obj: MessageMediaDocument) -> MessageMediaDocument_136:
        kwargs = from_obj.to_dict()
        del kwargs["nopremium"]
        del kwargs["spoiler"]
        del kwargs["video"]
        del kwargs["round"]
        del kwargs["voice"]
        del kwargs["alt_document"]

        return MessageMediaDocument_136(**kwargs)


class MessageMediaDocumentDontDowngrade(BaseDowngrader):
    BASE_TYPE = MessageMediaDocument
    TARGET_LAYER = 177

    @classmethod
    def downgrade(cls, from_obj: MessageMediaDocument) -> MessageMediaDocument:
        return copy(from_obj)
