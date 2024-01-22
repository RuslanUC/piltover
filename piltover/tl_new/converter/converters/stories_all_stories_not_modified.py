from piltover.tl_new.types.stories import AllStoriesNotModified, AllStoriesNotModified_160
from piltover.tl_new.converter import ConverterBase


class AllStoriesNotModifiedConverter(ConverterBase):
    base = AllStoriesNotModified
    old = [AllStoriesNotModified_160]
    layers = [160]

    @staticmethod
    def from_160(obj: AllStoriesNotModified_160) -> AllStoriesNotModified:
        data = obj.to_dict()
        assert False, "required field 'stealth_mode' added in base tl object"  # TODO: add field
        return AllStoriesNotModified(**data)

    @staticmethod
    def to_160(obj: AllStoriesNotModified) -> AllStoriesNotModified_160:
        data = obj.to_dict()
        del data["stealth_mode"]
        del data["flags"]
        return AllStoriesNotModified_160(**data)

