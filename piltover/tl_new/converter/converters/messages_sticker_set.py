from piltover.tl_new.types.messages import StickerSet, StickerSet_136
from piltover.tl_new.converter import ConverterBase


class StickerSetConverter(ConverterBase):
    base = StickerSet
    old = [StickerSet_136]
    layers = [136]

    @staticmethod
    def from_136(obj: StickerSet_136) -> StickerSet:
        data = obj.to_dict()
        assert False, "required field 'keywords' added in base tl object"  # TODO: add field
        return StickerSet(**data)

    @staticmethod
    def to_136(obj: StickerSet) -> StickerSet_136:
        data = obj.to_dict()
        del data["keywords"]
        return StickerSet_136(**data)

