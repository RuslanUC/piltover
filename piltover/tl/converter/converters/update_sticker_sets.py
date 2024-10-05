from piltover.tl.converter import ConverterBase
from piltover.tl.types import UpdateStickerSets, UpdateStickerSets_136


class UpdateStickerSetsConverter(ConverterBase):
    base = UpdateStickerSets
    old = [UpdateStickerSets_136]
    layers = [136]

    @staticmethod
    def from_136(obj: UpdateStickerSets_136) -> UpdateStickerSets:
        data = obj.to_dict()
        return UpdateStickerSets(**data)

    @staticmethod
    def to_136(obj: UpdateStickerSets) -> UpdateStickerSets_136:
        data = obj.to_dict()
        del data["masks"]
        del data["emojis"]
        del data["flags"]
        return UpdateStickerSets_136(**data)
