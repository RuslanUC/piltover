from piltover.tl_new.functions.stories import DeleteStories, DeleteStories_160
from piltover.tl_new.converter import ConverterBase


class DeleteStoriesConverter(ConverterBase):
    base = DeleteStories
    old = [DeleteStories_160]
    layers = [160]

    @staticmethod
    def from_160(obj: DeleteStories_160) -> DeleteStories:
        data = obj.to_dict()
        assert False, "required field 'peer' added in base tl object"  # TODO: add field
        return DeleteStories(**data)

    @staticmethod
    def to_160(obj: DeleteStories) -> DeleteStories_160:
        data = obj.to_dict()
        del data["peer"]
        return DeleteStories_160(**data)

