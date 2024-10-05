from piltover.tl import InputPeerEmpty
from piltover.tl.converter import ConverterBase
from piltover.tl.functions.stories import DeleteStories, DeleteStories_160


class DeleteStoriesConverter(ConverterBase):
    base = DeleteStories
    old = [DeleteStories_160]
    layers = [160]

    @staticmethod
    def from_160(obj: DeleteStories_160) -> DeleteStories:
        data = obj.to_dict()
        data["peer"] = InputPeerEmpty()
        return DeleteStories(**data)

    @staticmethod
    def to_160(obj: DeleteStories) -> DeleteStories_160:
        data = obj.to_dict()
        del data["peer"]
        return DeleteStories_160(**data)
