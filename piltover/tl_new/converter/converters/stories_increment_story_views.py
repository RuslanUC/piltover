from piltover.tl_new import PeerUser
from piltover.tl_new.converter import ConverterBase
from piltover.tl_new.functions.stories import IncrementStoryViews, IncrementStoryViews_160


class IncrementStoryViewsConverter(ConverterBase):
    base = IncrementStoryViews
    old = [IncrementStoryViews_160]
    layers = [160]

    @staticmethod
    def from_160(obj: IncrementStoryViews_160) -> IncrementStoryViews:
        data = obj.to_dict()
        data["peer"] = PeerUser(user_id=obj.user_id)
        del data["user_id"]
        return IncrementStoryViews(**data)

    @staticmethod
    def to_160(obj: IncrementStoryViews) -> IncrementStoryViews_160:
        data = obj.to_dict()
        del data["peer"]
        data["user_id"] = obj.peer.user_id
        return IncrementStoryViews_160(**data)
