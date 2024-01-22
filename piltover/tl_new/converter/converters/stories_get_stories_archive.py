from piltover.tl_new.functions.stories import GetStoriesArchive, GetStoriesArchive_160
from piltover.tl_new.converter import ConverterBase


class GetStoriesArchiveConverter(ConverterBase):
    base = GetStoriesArchive
    old = [GetStoriesArchive_160]
    layers = [160]

    @staticmethod
    def from_160(obj: GetStoriesArchive_160) -> GetStoriesArchive:
        data = obj.to_dict()
        assert False, "required field 'peer' added in base tl object"  # TODO: add field
        return GetStoriesArchive(**data)

    @staticmethod
    def to_160(obj: GetStoriesArchive) -> GetStoriesArchive_160:
        data = obj.to_dict()
        del data["peer"]
        return GetStoriesArchive_160(**data)

