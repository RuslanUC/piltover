from piltover.tl_new.functions.stories import GetStoriesViews, GetStoriesViews_160
from piltover.tl_new.converter import ConverterBase


class GetStoriesViewsConverter(ConverterBase):
    base = GetStoriesViews
    old = [GetStoriesViews_160]
    layers = [160]

    @staticmethod
    def from_160(obj: GetStoriesViews_160) -> GetStoriesViews:
        data = obj.to_dict()
        assert False, "required field 'peer' added in base tl object"  # TODO: add field
        return GetStoriesViews(**data)

    @staticmethod
    def to_160(obj: GetStoriesViews) -> GetStoriesViews_160:
        data = obj.to_dict()
        del data["peer"]
        return GetStoriesViews_160(**data)

