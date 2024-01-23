from piltover.tl_new import UserStories_160, PeerStories, PeerUser, StoriesStealthMode
from piltover.tl_new.converter import ConverterBase
from piltover.tl_new.types.stories import AllStories, AllStories_160, AllStories_161


class AllStoriesConverter(ConverterBase):
    base = AllStories
    old = [AllStories_160, AllStories_161]
    layers = [160, 161]

    @staticmethod
    def from_160(obj: AllStories_160) -> AllStories:
        data = obj.to_dict()
        data["chats"] = []
        data["peer_stories"] = [
            PeerStories(peer=PeerUser(user_id=story.user_id), stories=story.stories, max_read_id=story.max_read_id)
            for story in obj.user_stories
        ]
        data["stealth_mode"] = StoriesStealthMode()
        del data["user_stories"]
        return AllStories(**data)

    @staticmethod
    def to_160(obj: AllStories) -> AllStories_160:
        data = obj.to_dict()
        del data["peer_stories"]
        del data["stealth_mode"]
        del data["chats"]
        data["user_stories"] = [
            UserStories_160(user_id=story.peer.user_id, stories=story.stories, max_read_id=story.max_read_id)
            for story in obj.peer_stories if isinstance(story.peer, PeerUser)
        ]
        return AllStories_160(**data)

    @staticmethod
    def from_161(obj: AllStories_161) -> AllStories:
        data = obj.to_dict()
        data["chats"] = []
        data["peer_stories"] = [
            PeerStories(peer=PeerUser(user_id=story.user_id), stories=story.stories, max_read_id=story.max_read_id)
            for story in obj.user_stories
        ]
        del data["user_stories"]
        return AllStories(**data)

    @staticmethod
    def to_161(obj: AllStories) -> AllStories_161:
        data = obj.to_dict()
        del data["peer_stories"]
        del data["chats"]
        data["user_stories"] = [
            UserStories_160(user_id=story.peer.user_id, stories=story.stories, max_read_id=story.max_read_id)
            for story in obj.peer_stories if isinstance(story.peer, PeerUser)
        ]
        return AllStories_161(**data)
