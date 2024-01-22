from piltover.tl_new.types import UpdateChannelReadMessagesContents, UpdateChannelReadMessagesContents_136
from piltover.tl_new.converter import ConverterBase


class UpdateChannelReadMessagesContentsConverter(ConverterBase):
    base = UpdateChannelReadMessagesContents
    old = [UpdateChannelReadMessagesContents_136]
    layers = [136]

    @staticmethod
    def from_136(obj: UpdateChannelReadMessagesContents_136) -> UpdateChannelReadMessagesContents:
        data = obj.to_dict()
        return UpdateChannelReadMessagesContents(**data)

    @staticmethod
    def to_136(obj: UpdateChannelReadMessagesContents) -> UpdateChannelReadMessagesContents_136:
        data = obj.to_dict()
        del data["flags"]
        del data["top_msg_id"]
        return UpdateChannelReadMessagesContents_136(**data)

