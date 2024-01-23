from piltover.tl_new.converter import ConverterBase
from piltover.tl_new.functions.photos import UpdateProfilePhoto, UpdateProfilePhoto_136, UpdateProfilePhoto_151


class UpdateProfilePhotoConverter(ConverterBase):
    base = UpdateProfilePhoto
    old = [UpdateProfilePhoto_136, UpdateProfilePhoto_151]
    layers = [136, 151]

    @staticmethod
    def from_136(obj: UpdateProfilePhoto_136) -> UpdateProfilePhoto:
        data = obj.to_dict()
        return UpdateProfilePhoto(**data)

    @staticmethod
    def to_136(obj: UpdateProfilePhoto) -> UpdateProfilePhoto_136:
        data = obj.to_dict()
        del data["fallback"]
        del data["bot"]
        del data["flags"]
        return UpdateProfilePhoto_136(**data)

    @staticmethod
    def from_151(obj: UpdateProfilePhoto_151) -> UpdateProfilePhoto:
        data = obj.to_dict()
        return UpdateProfilePhoto(**data)

    @staticmethod
    def to_151(obj: UpdateProfilePhoto) -> UpdateProfilePhoto_151:
        data = obj.to_dict()
        del data["bot"]
        return UpdateProfilePhoto_151(**data)
