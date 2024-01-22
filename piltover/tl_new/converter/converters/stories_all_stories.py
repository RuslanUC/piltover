from piltover.tl_new.types.stories import AllStories, AllStories_160, AllStories_161
from piltover.tl_new.converter import ConverterBase


class AllStoriesConverter(ConverterBase):
    base = AllStories
    old = [AllStories_160, AllStories_161]
    layers = [160, 161]

    @staticmethod
    def from_160(obj: AllStories_160) -> AllStories:
        data = obj.to_dict()
        assert False, "required field 'peer_stories' added in base tl object"  # TODO: add field
        assert False, "required field 'stealth_mode' added in base tl object"  # TODO: add field
        assert False, "required field 'chats' added in base tl object"  # TODO: add field
        del data["user_stories"]
        return AllStories(**data)

    @staticmethod
    def to_160(obj: AllStories) -> AllStories_160:
        data = obj.to_dict()
        del data["peer_stories"]
        del data["stealth_mode"]
        del data["chats"]
        assert False, "required field 'user_stories' deleted in base tl object"  # TODO: delete field
        return AllStories_160(**data)

    @staticmethod
    def from_161(obj: AllStories_161) -> AllStories:
        data = obj.to_dict()
        assert False, "required field 'peer_stories' added in base tl object"  # TODO: add field
        assert False, "required field 'chats' added in base tl object"  # TODO: add field
        del data["user_stories"]
        return AllStories(**data)

    @staticmethod
    def to_161(obj: AllStories) -> AllStories_161:
        data = obj.to_dict()
        del data["peer_stories"]
        del data["chats"]
        assert False, "required field 'user_stories' deleted in base tl object"  # TODO: delete field
        return AllStories_161(**data)

