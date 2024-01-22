from piltover.tl_new.types.messages import ChannelMessages, ChannelMessages_136
from piltover.tl_new.converter import ConverterBase


class ChannelMessagesConverter(ConverterBase):
    base = ChannelMessages
    old = [ChannelMessages_136]
    layers = [136]

    @staticmethod
    def from_136(obj: ChannelMessages_136) -> ChannelMessages:
        data = obj.to_dict()
        data["topics"] = []
        return ChannelMessages(**data)

    @staticmethod
    def to_136(obj: ChannelMessages) -> ChannelMessages_136:
        data = obj.to_dict()
        del data["topics"]
        return ChannelMessages_136(**data)

