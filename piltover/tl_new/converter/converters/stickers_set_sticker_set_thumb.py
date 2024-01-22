from piltover.tl_new.functions.stickers import SetStickerSetThumb, SetStickerSetThumb_136
from piltover.tl_new.converter import ConverterBase


class SetStickerSetThumbConverter(ConverterBase):
    base = SetStickerSetThumb
    old = [SetStickerSetThumb_136]
    layers = [136]

    @staticmethod
    def from_136(obj: SetStickerSetThumb_136) -> SetStickerSetThumb:
        data = obj.to_dict()
        assert False, "type of field 'thumb' changed (InputDocument -> flags.0?InputDocument)"  # TODO: type changed
        return SetStickerSetThumb(**data)

    @staticmethod
    def to_136(obj: SetStickerSetThumb) -> SetStickerSetThumb_136:
        data = obj.to_dict()
        del data["thumb_document_id"]
        del data["flags"]
        assert False, "type of field 'thumb' changed (flags.0?InputDocument -> InputDocument)"  # TODO: type changed
        return SetStickerSetThumb_136(**data)

