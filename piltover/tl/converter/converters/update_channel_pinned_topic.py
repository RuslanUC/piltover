from piltover.tl.converter import ConverterBase
from piltover.tl.types import UpdateChannelPinnedTopic, UpdateChannelPinnedTopic_148


class UpdateChannelPinnedTopicConverter(ConverterBase):
    base = UpdateChannelPinnedTopic
    old = [UpdateChannelPinnedTopic_148]
    layers = [148]

    @staticmethod
    def from_148(obj: UpdateChannelPinnedTopic_148) -> UpdateChannelPinnedTopic:
        data = obj.to_dict()
        if data["topic_id"] is None:
            data["topic_id"] = 0
        return UpdateChannelPinnedTopic(**data)

    @staticmethod
    def to_148(obj: UpdateChannelPinnedTopic) -> UpdateChannelPinnedTopic_148:
        data = obj.to_dict()
        del data["pinned"]
        return UpdateChannelPinnedTopic_148(**data)
