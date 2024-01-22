from piltover.tl_new import PeerUser
from piltover.tl_new.functions.stories import ReadStories, ReadStories_160
from piltover.tl_new.converter import ConverterBase


class ReadStoriesConverter(ConverterBase):
    base = ReadStories
    old = [ReadStories_160]
    layers = [160]

    @staticmethod
    def from_160(obj: ReadStories_160) -> ReadStories:
        data = obj.to_dict()
        data["peer"] = PeerUser(user_id=obj.user_id)
        del data["user_id"]
        return ReadStories(**data)

    @staticmethod
    def to_160(obj: ReadStories) -> ReadStories_160:
        data = obj.to_dict()
        del data["peer"]
        assert False, "required field 'user_id' deleted in base tl object"  # TODO: delete field
        return ReadStories_160(**data)

