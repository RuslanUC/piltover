from piltover.tl import PeerUser
from piltover.tl.converter import ConverterBase
from piltover.tl.types import UpdateStory, UpdateStory_160


class UpdateStoryConverter(ConverterBase):
    base = UpdateStory
    old = [UpdateStory_160]
    layers = [160]

    @staticmethod
    def from_160(obj: UpdateStory_160) -> UpdateStory:
        data = obj.to_dict()
        data["peer"] = PeerUser(user_id=obj.user_id)
        del data["user_id"]
        return UpdateStory(**data)

    @staticmethod
    def to_160(obj: UpdateStory) -> UpdateStory_160:
        data = obj.to_dict()
        del data["peer"]
        data["user_id"] = obj.peer.user_id
        return UpdateStory_160(**data)
