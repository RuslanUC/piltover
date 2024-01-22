from piltover.tl_new.functions.photos import UploadContactProfilePhoto, UploadContactProfilePhoto_151
from piltover.tl_new.converter import ConverterBase


class UploadContactProfilePhotoConverter(ConverterBase):
    base = UploadContactProfilePhoto
    old = [UploadContactProfilePhoto_151]
    layers = [151]

    @staticmethod
    def from_151(obj: UploadContactProfilePhoto_151) -> UploadContactProfilePhoto:
        data = obj.to_dict()
        return UploadContactProfilePhoto(**data)

    @staticmethod
    def to_151(obj: UploadContactProfilePhoto) -> UploadContactProfilePhoto_151:
        data = obj.to_dict()
        del data["video_emoji_markup"]
        return UploadContactProfilePhoto_151(**data)

