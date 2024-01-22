from piltover.tl_new.functions.stories import EditStory, EditStory_160, EditStory_161
from piltover.tl_new.converter import ConverterBase


class EditStoryConverter(ConverterBase):
    base = EditStory
    old = [EditStory_160, EditStory_161]
    layers = [160, 161]

    @staticmethod
    def from_160(obj: EditStory_160) -> EditStory:
        data = obj.to_dict()
        assert False, "required field 'peer' added in base tl object"  # TODO: add field
        return EditStory(**data)

    @staticmethod
    def to_160(obj: EditStory) -> EditStory_160:
        data = obj.to_dict()
        del data["media_areas"]
        del data["peer"]
        return EditStory_160(**data)

    @staticmethod
    def from_161(obj: EditStory_161) -> EditStory:
        data = obj.to_dict()
        assert False, "required field 'peer' added in base tl object"  # TODO: add field
        return EditStory(**data)

    @staticmethod
    def to_161(obj: EditStory) -> EditStory_161:
        data = obj.to_dict()
        del data["peer"]
        return EditStory_161(**data)

