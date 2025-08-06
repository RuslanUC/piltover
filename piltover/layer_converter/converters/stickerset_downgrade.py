from piltover.layer_converter.converters.base import AutoDowngrader
from piltover.tl.types import StickerSet, StickerSet_136


class StickerSetDowngradeTo136(AutoDowngrader):
    BASE_TYPE = StickerSet
    TARGET_TYPE = StickerSet_136
    TARGET_LAYER = 136
    REMOVE_FIELDS = {"text_color", "channel_emoji_status", "creator", "thumb_document_id"}


class StickerSetDontDowngrade144(AutoDowngrader):
    BASE_TYPE = StickerSet
    TARGET_TYPE = StickerSet
    TARGET_LAYER = 144
    REMOVE_FIELDS = set()


class StickerSetDontDowngrade(AutoDowngrader):
    BASE_TYPE = StickerSet
    TARGET_TYPE = StickerSet
    TARGET_LAYER = 201
    REMOVE_FIELDS = set()
