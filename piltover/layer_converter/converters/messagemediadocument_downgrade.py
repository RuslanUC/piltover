from piltover.layer_converter.converters.base import AutoDowngrader
from piltover.tl import MessageMediaDocument, MessageMediaDocument_133, MessageMediaDocument_160, \
    MessageMediaDocument_189


class MessageMediaDocumentDowngradeTo133(AutoDowngrader):
    BASE_TYPE = MessageMediaDocument
    TARGET_TYPE = MessageMediaDocument_133
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = {
        "nopremium", "spoiler", "video", "round", "voice", "alt_documents", "video_cover", "video_timestamp",
    }


class MessageMediaDocumentDowngradeTo160(AutoDowngrader):
    BASE_TYPE = MessageMediaDocument
    TARGET_TYPE = MessageMediaDocument_160
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = {"video", "round", "voice", "alt_documents", "video_cover", "video_timestamp"}


class MessageMediaDocumentDowngradeTo189(AutoDowngrader):
    BASE_TYPE = MessageMediaDocument
    TARGET_TYPE = MessageMediaDocument_189
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = {"video_cover", "video_timestamp"}


class MessageMediaDocumentDontDowngrade(AutoDowngrader):
    BASE_TYPE = MessageMediaDocument
    TARGET_TYPE = MessageMediaDocument
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = set()
