from piltover.tl import InputPeerEmpty
from piltover.tl.converter import ConverterBase
from piltover.tl.functions.stories import CanSendStory, CanSendStory_162


class CanSendStoryConverter(ConverterBase):
    base = CanSendStory
    old = [CanSendStory_162]
    layers = [162]

    @staticmethod
    def from_162(obj: CanSendStory_162) -> CanSendStory:
        data = obj.to_dict()
        data["peer"] = InputPeerEmpty()
        return CanSendStory(**data)

    @staticmethod
    def to_162(obj: CanSendStory) -> CanSendStory_162:
        data = obj.to_dict()
        del data["peer"]
        return CanSendStory_162(**data)
