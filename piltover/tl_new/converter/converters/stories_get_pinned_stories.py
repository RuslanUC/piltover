from piltover.tl_new import InputUser, InputPeerUser
from piltover.tl_new.converter import ConverterBase
from piltover.tl_new.functions.stories import GetPinnedStories, GetPinnedStories_160


class GetPinnedStoriesConverter(ConverterBase):
    base = GetPinnedStories
    old = [GetPinnedStories_160]
    layers = [160]

    @staticmethod
    def from_160(obj: GetPinnedStories_160) -> GetPinnedStories:
        data = obj.to_dict()
        data["peer"] = InputPeerUser(user_id=obj.user_id, access_hash=obj.user_id.access_hash)
        del data["user_id"]
        return GetPinnedStories(**data)

    @staticmethod
    def to_160(obj: GetPinnedStories) -> GetPinnedStories_160:
        data = obj.to_dict()
        del data["peer"]
        data["peer"] = InputUser(user_id=obj.peer.user_id, access_hash=obj.peer.access_hash)
        return GetPinnedStories_160(**data)
