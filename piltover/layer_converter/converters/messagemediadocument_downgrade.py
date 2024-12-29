from piltover.layer_converter.converters.base import AutoDowngrader
from piltover.tl import MessageMediaDocument, MessageMediaDocument_136


class MessageMediaDocumentDowngradeTo136(AutoDowngrader):
    BASE_TYPE = MessageMediaDocument
    TARGET_LAYER = 136
    TARGET_TYPE = MessageMediaDocument_136
    REMOVE_FIELDS = {"nopremium", "spoiler", "video", "round", "voice", "alt_document"}


class MessageMediaDocumentDontDowngrade(AutoDowngrader):
    BASE_TYPE = MessageMediaDocument
    TARGET_LAYER = 177
    TARGET_TYPE = MessageMediaDocument
    REMOVE_FIELDS = set()
