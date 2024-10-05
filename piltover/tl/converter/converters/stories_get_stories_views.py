from piltover.tl import InputPeerEmpty
from piltover.tl.converter import ConverterBase
from piltover.tl.functions.stories import GetStoriesViews, GetStoriesViews_160


class GetStoriesViewsConverter(ConverterBase):
    base = GetStoriesViews
    old = [GetStoriesViews_160]
    layers = [160]

    @staticmethod
    def from_160(obj: GetStoriesViews_160) -> GetStoriesViews:
        data = obj.to_dict()
        data["peer"] = InputPeerEmpty()
        return GetStoriesViews(**data)

    @staticmethod
    def to_160(obj: GetStoriesViews) -> GetStoriesViews_160:
        data = obj.to_dict()
        del data["peer"]
        return GetStoriesViews_160(**data)
