from piltover.tl import PeerUser
from piltover.tl.converter import ConverterBase
from piltover.tl.types import UpdateReadStories, UpdateReadStories_160


class UpdateReadStoriesConverter(ConverterBase):
    base = UpdateReadStories
    old = [UpdateReadStories_160]
    layers = [160]

    @staticmethod
    def from_160(obj: UpdateReadStories_160) -> UpdateReadStories:
        data = obj.to_dict()
        data["peer"] = PeerUser(user_id=obj.user_id)
        del data["user_id"]
        return UpdateReadStories(**data)

    @staticmethod
    def to_160(obj: UpdateReadStories) -> UpdateReadStories_160:
        data = obj.to_dict()
        del data["peer"]
        data["user_id"] = obj.peer.user_id
        return UpdateReadStories_160(**data)
