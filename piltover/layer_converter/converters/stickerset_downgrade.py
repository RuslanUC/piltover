from piltover.layer_converter.converters.base import AutoDowngrader
from piltover.tl.types import StickerSet, StickerSet_133


class StickerSetDowngradeTo133(AutoDowngrader):
    BASE_TYPE = StickerSet
    TARGET_TYPE = StickerSet_133
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = {"text_color", "channel_emoji_status", "creator", "thumb_document_id"}


class StickerSetDontDowngrade(AutoDowngrader):
    BASE_TYPE = StickerSet
    TARGET_TYPE = StickerSet
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = set()
