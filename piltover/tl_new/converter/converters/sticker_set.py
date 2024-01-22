from piltover.tl_new.types import StickerSet, StickerSet_136
from piltover.tl_new.converter import ConverterBase


class StickerSetConverter(ConverterBase):
    base = StickerSet
    old = [StickerSet_136]
    layers = [136]

    @staticmethod
    def from_136(obj: StickerSet_136) -> StickerSet:
        data = obj.to_dict()
        return StickerSet(**data)

    @staticmethod
    def to_136(obj: StickerSet) -> StickerSet_136:
        data = obj.to_dict()
        del data["thumb_document_id"]
        del data["text_color"]
        return StickerSet_136(**data)

