from piltover.tl.converter import ConverterBase
from piltover.tl.types import StickerSetFullCovered, StickerSetFullCovered_144


class StickerSetFullCoveredConverter(ConverterBase):
    base = StickerSetFullCovered
    old = [StickerSetFullCovered_144]
    layers = [144]

    @staticmethod
    def from_144(obj: StickerSetFullCovered_144) -> StickerSetFullCovered:
        data = obj.to_dict()
        data["keywords"] = []
        return StickerSetFullCovered(**data)

    @staticmethod
    def to_144(obj: StickerSetFullCovered) -> StickerSetFullCovered_144:
        data = obj.to_dict()
        del data["keywords"]
        return StickerSetFullCovered_144(**data)
