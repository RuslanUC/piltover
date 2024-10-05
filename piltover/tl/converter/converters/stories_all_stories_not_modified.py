from piltover.tl import StoriesStealthMode
from piltover.tl.converter import ConverterBase
from piltover.tl.types.stories import AllStoriesNotModified, AllStoriesNotModified_160


class AllStoriesNotModifiedConverter(ConverterBase):
    base = AllStoriesNotModified
    old = [AllStoriesNotModified_160]
    layers = [160]

    @staticmethod
    def from_160(obj: AllStoriesNotModified_160) -> AllStoriesNotModified:
        data = obj.to_dict()
        data["stealth_mode"] = StoriesStealthMode()
        return AllStoriesNotModified(**data)

    @staticmethod
    def to_160(obj: AllStoriesNotModified) -> AllStoriesNotModified_160:
        data = obj.to_dict()
        del data["stealth_mode"]
        del data["flags"]
        return AllStoriesNotModified_160(**data)
