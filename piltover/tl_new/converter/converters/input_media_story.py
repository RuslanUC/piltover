from piltover.tl_new import PeerUser
from piltover.tl_new.types import InputMediaStory, InputMediaStory_160
from piltover.tl_new.converter import ConverterBase


class InputMediaStoryConverter(ConverterBase):
    base = InputMediaStory
    old = [InputMediaStory_160]
    layers = [160]

    @staticmethod
    def from_160(obj: InputMediaStory_160) -> InputMediaStory:
        data = obj.to_dict()
        data["peer"] = PeerUser(user_id=obj.user_id)
        del data["user_id"]
        return InputMediaStory(**data)

    @staticmethod
    def to_160(obj: InputMediaStory) -> InputMediaStory_160:
        data = obj.to_dict()
        del data["peer"]
        data["user_id"] = obj.peer.user_id
        return InputMediaStory_160(**data)

