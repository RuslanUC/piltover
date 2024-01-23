from piltover.tl_new.converter import ConverterBase
from piltover.tl_new.types.messages import FeaturedStickers, FeaturedStickers_136


class FeaturedStickersConverter(ConverterBase):
    base = FeaturedStickers
    old = [FeaturedStickers_136]
    layers = [136]

    @staticmethod
    def from_136(obj: FeaturedStickers_136) -> FeaturedStickers:
        data = obj.to_dict()
        return FeaturedStickers(**data)

    @staticmethod
    def to_136(obj: FeaturedStickers) -> FeaturedStickers_136:
        data = obj.to_dict()
        del data["premium"]
        del data["flags"]
        return FeaturedStickers_136(**data)
