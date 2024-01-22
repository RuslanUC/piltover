from piltover.tl_new.functions.stories import CanSendStory, CanSendStory_162
from piltover.tl_new.converter import ConverterBase


class CanSendStoryConverter(ConverterBase):
    base = CanSendStory
    old = [CanSendStory_162]
    layers = [162]

    @staticmethod
    def from_162(obj: CanSendStory_162) -> CanSendStory:
        data = obj.to_dict()
        assert False, "required field 'peer' added in base tl object"  # TODO: add field
        return CanSendStory(**data)

    @staticmethod
    def to_162(obj: CanSendStory) -> CanSendStory_162:
        data = obj.to_dict()
        del data["peer"]
        return CanSendStory_162(**data)

