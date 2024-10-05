from piltover.tl import InputPeerEmpty
from piltover.tl.converter import ConverterBase
from piltover.tl.functions.stories import GetStoriesArchive, GetStoriesArchive_160


class GetStoriesArchiveConverter(ConverterBase):
    base = GetStoriesArchive
    old = [GetStoriesArchive_160]
    layers = [160]

    @staticmethod
    def from_160(obj: GetStoriesArchive_160) -> GetStoriesArchive:
        data = obj.to_dict()
        data["peer"] = InputPeerEmpty()
        return GetStoriesArchive(**data)

    @staticmethod
    def to_160(obj: GetStoriesArchive) -> GetStoriesArchive_160:
        data = obj.to_dict()
        del data["peer"]
        return GetStoriesArchive_160(**data)
