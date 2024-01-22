from piltover.tl_new.types.stories import StoryViewsList, StoryViewsList_160
from piltover.tl_new.converter import ConverterBase


class StoryViewsListConverter(ConverterBase):
    base = StoryViewsList
    old = [StoryViewsList_160]
    layers = [160]

    @staticmethod
    def from_160(obj: StoryViewsList_160) -> StoryViewsList:
        data = obj.to_dict()
        assert False, "required field 'reactions_count' added in base tl object"  # TODO: add field
        return StoryViewsList(**data)

    @staticmethod
    def to_160(obj: StoryViewsList) -> StoryViewsList_160:
        data = obj.to_dict()
        del data["reactions_count"]
        del data["flags"]
        del data["next_offset"]
        return StoryViewsList_160(**data)

