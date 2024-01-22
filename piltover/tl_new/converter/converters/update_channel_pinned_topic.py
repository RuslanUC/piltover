from piltover.tl_new.types import UpdateChannelPinnedTopic, UpdateChannelPinnedTopic_148
from piltover.tl_new.converter import ConverterBase


class UpdateChannelPinnedTopicConverter(ConverterBase):
    base = UpdateChannelPinnedTopic
    old = [UpdateChannelPinnedTopic_148]
    layers = [148]

    @staticmethod
    def from_148(obj: UpdateChannelPinnedTopic_148) -> UpdateChannelPinnedTopic:
        data = obj.to_dict()
        assert False, "type of field 'topic_id' changed (flags.0?int -> int)"  # TODO: type changed
        return UpdateChannelPinnedTopic(**data)

    @staticmethod
    def to_148(obj: UpdateChannelPinnedTopic) -> UpdateChannelPinnedTopic_148:
        data = obj.to_dict()
        del data["pinned"]
        assert False, "type of field 'topic_id' changed (int -> flags.0?int)"  # TODO: type changed
        return UpdateChannelPinnedTopic_148(**data)

