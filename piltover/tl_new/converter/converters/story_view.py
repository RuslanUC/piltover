from piltover.tl_new.converter import ConverterBase
from piltover.tl_new.types import StoryView, StoryView_160


class StoryViewConverter(ConverterBase):
    base = StoryView
    old = [StoryView_160]
    layers = [160]

    @staticmethod
    def from_160(obj: StoryView_160) -> StoryView:
        data = obj.to_dict()
        return StoryView(**data)

    @staticmethod
    def to_160(obj: StoryView) -> StoryView_160:
        data = obj.to_dict()
        del data["reaction"]
        del data["blocked_my_stories_from"]
        del data["blocked"]
        del data["flags"]
        return StoryView_160(**data)
