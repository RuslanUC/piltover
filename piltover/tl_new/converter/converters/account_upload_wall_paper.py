from piltover.tl_new.converter import ConverterBase
from piltover.tl_new.functions.account import UploadWallPaper, UploadWallPaper_136


class UploadWallPaperConverter(ConverterBase):
    base = UploadWallPaper
    old = [UploadWallPaper_136]
    layers = [136]

    @staticmethod
    def from_136(obj: UploadWallPaper_136) -> UploadWallPaper:
        data = obj.to_dict()
        return UploadWallPaper(**data)

    @staticmethod
    def to_136(obj: UploadWallPaper) -> UploadWallPaper_136:
        data = obj.to_dict()
        del data["for_chat"]
        del data["flags"]
        return UploadWallPaper_136(**data)
