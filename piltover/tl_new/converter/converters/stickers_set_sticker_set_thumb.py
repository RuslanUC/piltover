from piltover.tl_new import InputDocument
from piltover.tl_new.converter import ConverterBase
from piltover.tl_new.functions.stickers import SetStickerSetThumb, SetStickerSetThumb_136


class SetStickerSetThumbConverter(ConverterBase):
    base = SetStickerSetThumb
    old = [SetStickerSetThumb_136]
    layers = [136]

    @staticmethod
    def from_136(obj: SetStickerSetThumb_136) -> SetStickerSetThumb:
        data = obj.to_dict()
        return SetStickerSetThumb(**data)

    @staticmethod
    def to_136(obj: SetStickerSetThumb) -> SetStickerSetThumb_136:
        data = obj.to_dict()
        del data["thumb_document_id"]
        del data["flags"]
        if data["thumb"] is None:
            data["thumb"] = InputDocument(id=0, access_hash=0, file_reference=b"")
        return SetStickerSetThumb_136(**data)
