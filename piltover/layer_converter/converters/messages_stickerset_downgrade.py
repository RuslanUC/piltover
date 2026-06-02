from piltover.layer_converter.converters.base import AutoDowngrader
from piltover.tl.types.messages import StickerSet, StickerSet_133


class MessagesStickerSetDowngradeTo133(AutoDowngrader):
    BASE_TYPE = StickerSet
    TARGET_TYPE = StickerSet_133
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = {"keywords"}


class MessagesStickerSetDontDowngrade(AutoDowngrader):
    BASE_TYPE = StickerSet
    TARGET_TYPE = StickerSet
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = set()
