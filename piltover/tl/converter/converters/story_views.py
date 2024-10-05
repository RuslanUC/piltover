from piltover.tl.converter import ConverterBase
from piltover.tl.types import StoryViews, StoryViews_160, StoryViews_161


class StoryViewsConverter(ConverterBase):
    base = StoryViews
    old = [StoryViews_160, StoryViews_161]
    layers = [160, 161]

    @staticmethod
    def from_160(obj: StoryViews_160) -> StoryViews:
        data = obj.to_dict()
        return StoryViews(**data)

    @staticmethod
    def to_160(obj: StoryViews) -> StoryViews_160:
        data = obj.to_dict()
        del data["has_viewers"]
        del data["reactions"]
        del data["forwards_count"]
        del data["reactions_count"]
        return StoryViews_160(**data)

    @staticmethod
    def from_161(obj: StoryViews_161) -> StoryViews:
        data = obj.to_dict()
        return StoryViews(**data)

    @staticmethod
    def to_161(obj: StoryViews) -> StoryViews_161:
        data = obj.to_dict()
        del data["has_viewers"]
        del data["reactions"]
        del data["forwards_count"]
        if data["reactions_count"] is None:
            data["reactions_count"] = 0
        return StoryViews_161(**data)
