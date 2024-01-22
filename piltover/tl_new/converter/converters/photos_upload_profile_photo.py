from piltover.tl_new.functions.photos import UploadProfilePhoto, UploadProfilePhoto_136, UploadProfilePhoto_152
from piltover.tl_new.converter import ConverterBase


class UploadProfilePhotoConverter(ConverterBase):
    base = UploadProfilePhoto
    old = [UploadProfilePhoto_136, UploadProfilePhoto_152]
    layers = [136, 152]

    @staticmethod
    def from_136(obj: UploadProfilePhoto_136) -> UploadProfilePhoto:
        data = obj.to_dict()
        return UploadProfilePhoto(**data)

    @staticmethod
    def to_136(obj: UploadProfilePhoto) -> UploadProfilePhoto_136:
        data = obj.to_dict()
        del data["video_emoji_markup"]
        del data["bot"]
        return UploadProfilePhoto_136(**data)

    @staticmethod
    def from_152(obj: UploadProfilePhoto_152) -> UploadProfilePhoto:
        data = obj.to_dict()
        return UploadProfilePhoto(**data)

    @staticmethod
    def to_152(obj: UploadProfilePhoto) -> UploadProfilePhoto_152:
        data = obj.to_dict()
        del data["bot"]
        return UploadProfilePhoto_152(**data)

