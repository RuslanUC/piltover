from piltover.tl_new import InputPeerEmpty
from piltover.tl_new.converter import ConverterBase
from piltover.tl_new.functions.stories import SendStory, SendStory_160, SendStory_161, SendStory_164


class SendStoryConverter(ConverterBase):
    base = SendStory
    old = [SendStory_160, SendStory_161, SendStory_164]
    layers = [160, 161, 164]

    @staticmethod
    def from_160(obj: SendStory_160) -> SendStory:
        data = obj.to_dict()
        data["peer"] = InputPeerEmpty()
        return SendStory(**data)

    @staticmethod
    def to_160(obj: SendStory) -> SendStory_160:
        data = obj.to_dict()
        del data["fwd_modified"]
        del data["fwd_from_story"]
        del data["media_areas"]
        del data["fwd_from_id"]
        del data["peer"]
        return SendStory_160(**data)

    @staticmethod
    def from_161(obj: SendStory_161) -> SendStory:
        data = obj.to_dict()
        data["peer"] = InputPeerEmpty()
        return SendStory(**data)

    @staticmethod
    def to_161(obj: SendStory) -> SendStory_161:
        data = obj.to_dict()
        del data["fwd_modified"]
        del data["fwd_from_story"]
        del data["fwd_from_id"]
        del data["peer"]
        return SendStory_161(**data)

    @staticmethod
    def from_164(obj: SendStory_164) -> SendStory:
        data = obj.to_dict()
        return SendStory(**data)

    @staticmethod
    def to_164(obj: SendStory) -> SendStory_164:
        data = obj.to_dict()
        del data["fwd_modified"]
        del data["fwd_from_story"]
        del data["fwd_from_id"]
        return SendStory_164(**data)
