from piltover.tl_new.types import UpdateReadMessagesContents, UpdateReadMessagesContents_136
from piltover.tl_new.converter import ConverterBase


class UpdateReadMessagesContentsConverter(ConverterBase):
    base = UpdateReadMessagesContents
    old = [UpdateReadMessagesContents_136]
    layers = [136]

    @staticmethod
    def from_136(obj: UpdateReadMessagesContents_136) -> UpdateReadMessagesContents:
        data = obj.to_dict()
        return UpdateReadMessagesContents(**data)

    @staticmethod
    def to_136(obj: UpdateReadMessagesContents) -> UpdateReadMessagesContents_136:
        data = obj.to_dict()
        del data["date"]
        del data["flags"]
        return UpdateReadMessagesContents_136(**data)

