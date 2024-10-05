from piltover.tl.converter import ConverterBase
from piltover.tl.types import InputStickerSetItem, InputStickerSetItem_136


class InputStickerSetItemConverter(ConverterBase):
    base = InputStickerSetItem
    old = [InputStickerSetItem_136]
    layers = [136]

    @staticmethod
    def from_136(obj: InputStickerSetItem_136) -> InputStickerSetItem:
        data = obj.to_dict()
        return InputStickerSetItem(**data)

    @staticmethod
    def to_136(obj: InputStickerSetItem) -> InputStickerSetItem_136:
        data = obj.to_dict()
        del data["keywords"]
        return InputStickerSetItem_136(**data)
