from piltover.tl_new import PeerUser
from piltover.tl_new.functions.stories import IncrementStoryViews, IncrementStoryViews_160
from piltover.tl_new.converter import ConverterBase


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
        assert False, "required field 'user_id' deleted in base tl object"  # TODO: delete field
        return IncrementStoryViews_160(**data)

