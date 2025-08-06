from piltover.layer_converter.converters.base import AutoDowngrader
from piltover.tl.types.messages import StickerSet, StickerSet_136


class MessagesStickerSetDowngradeTo136(AutoDowngrader):
    BASE_TYPE = StickerSet
    TARGET_TYPE = StickerSet_136
    TARGET_LAYER = 136
    REMOVE_FIELDS = {"keywords"}


class MessagesStickerSetDontDowngrade147(AutoDowngrader):
    BASE_TYPE = StickerSet
    TARGET_TYPE = StickerSet
    TARGET_LAYER = 147
    REMOVE_FIELDS = set()


class MessagesStickerSetDontDowngrade(AutoDowngrader):
    BASE_TYPE = StickerSet
    TARGET_TYPE = StickerSet
    TARGET_LAYER = 201
    REMOVE_FIELDS = set()
