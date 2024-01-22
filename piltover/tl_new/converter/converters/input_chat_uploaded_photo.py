from piltover.tl_new.types import InputChatUploadedPhoto, InputChatUploadedPhoto_136
from piltover.tl_new.converter import ConverterBase


class InputChatUploadedPhotoConverter(ConverterBase):
    base = InputChatUploadedPhoto
    old = [InputChatUploadedPhoto_136]
    layers = [136]

    @staticmethod
    def from_136(obj: InputChatUploadedPhoto_136) -> InputChatUploadedPhoto:
        data = obj.to_dict()
        return InputChatUploadedPhoto(**data)

    @staticmethod
    def to_136(obj: InputChatUploadedPhoto) -> InputChatUploadedPhoto_136:
        data = obj.to_dict()
        del data["video_emoji_markup"]
        return InputChatUploadedPhoto_136(**data)

