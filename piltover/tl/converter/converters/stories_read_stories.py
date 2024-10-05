from piltover.tl import PeerUser
from piltover.tl.converter import ConverterBase
from piltover.tl.functions.stories import ReadStories, ReadStories_160


class ReadStoriesConverter(ConverterBase):
    base = ReadStories
    old = [ReadStories_160]
    layers = [160]

    @staticmethod
    def from_160(obj: ReadStories_160) -> ReadStories:
        data = obj.to_dict()
        data["peer"] = PeerUser(user_id=obj.user_id.user_id)
        del data["user_id"]
        return ReadStories(**data)

    @staticmethod
    def to_160(obj: ReadStories) -> ReadStories_160:
        data = obj.to_dict()
        del data["peer"]
        data["user_id"] = obj.peer.user_id
        return ReadStories_160(**data)
