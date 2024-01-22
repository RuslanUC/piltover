from piltover.tl_new.functions.stories import GetPinnedStories, GetPinnedStories_160
from piltover.tl_new.converter import ConverterBase


class GetPinnedStoriesConverter(ConverterBase):
    base = GetPinnedStories
    old = [GetPinnedStories_160]
    layers = [160]

    @staticmethod
    def from_160(obj: GetPinnedStories_160) -> GetPinnedStories:
        data = obj.to_dict()
        assert False, "required field 'peer' added in base tl object"  # TODO: add field
        del data["user_id"]
        return GetPinnedStories(**data)

    @staticmethod
    def to_160(obj: GetPinnedStories) -> GetPinnedStories_160:
        data = obj.to_dict()
        del data["peer"]
        assert False, "required field 'user_id' deleted in base tl object"  # TODO: delete field
        return GetPinnedStories_160(**data)

