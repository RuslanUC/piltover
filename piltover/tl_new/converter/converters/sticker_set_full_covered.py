from piltover.tl_new.types import StickerSetFullCovered, StickerSetFullCovered_144
from piltover.tl_new.converter import ConverterBase


class StickerSetFullCoveredConverter(ConverterBase):
    base = StickerSetFullCovered
    old = [StickerSetFullCovered_144]
    layers = [144]

    @staticmethod
    def from_144(obj: StickerSetFullCovered_144) -> StickerSetFullCovered:
        data = obj.to_dict()
        assert False, "required field 'keywords' added in base tl object"  # TODO: add field
        return StickerSetFullCovered(**data)

    @staticmethod
    def to_144(obj: StickerSetFullCovered) -> StickerSetFullCovered_144:
        data = obj.to_dict()
        del data["keywords"]
        return StickerSetFullCovered_144(**data)

