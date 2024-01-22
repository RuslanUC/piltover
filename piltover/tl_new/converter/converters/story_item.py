from piltover.tl_new.types import StoryItem, StoryItem_160, StoryItem_161
from piltover.tl_new.converter import ConverterBase


class StoryItemConverter(ConverterBase):
    base = StoryItem
    old = [StoryItem_160, StoryItem_161]
    layers = [160, 161]

    @staticmethod
    def from_160(obj: StoryItem_160) -> StoryItem:
        data = obj.to_dict()
        return StoryItem(**data)

    @staticmethod
    def to_160(obj: StoryItem) -> StoryItem_160:
        data = obj.to_dict()
        del data["media_areas"]
        del data["out"]
        del data["fwd_from"]
        del data["sent_reaction"]
        return StoryItem_160(**data)

    @staticmethod
    def from_161(obj: StoryItem_161) -> StoryItem:
        data = obj.to_dict()
        return StoryItem(**data)

    @staticmethod
    def to_161(obj: StoryItem) -> StoryItem_161:
        data = obj.to_dict()
        del data["out"]
        del data["fwd_from"]
        return StoryItem_161(**data)

