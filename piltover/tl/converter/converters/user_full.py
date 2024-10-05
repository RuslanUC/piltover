from piltover.tl import PeerUser, UserStories_160, PeerStories
from piltover.tl.converter import ConverterBase
from piltover.tl.types import UserFull, UserFull_136, UserFull_140, UserFull_144, UserFull_151, UserFull_158, \
    UserFull_160


class UserFullConverter(ConverterBase):
    base = UserFull
    old = [UserFull_136, UserFull_140, UserFull_144, UserFull_151, UserFull_158, UserFull_160]
    layers = [136, 140, 144, 151, 158, 160]

    @staticmethod
    def from_136(obj: UserFull_136) -> UserFull:
        data = obj.to_dict()
        return UserFull(**data)

    @staticmethod
    def to_136(obj: UserFull) -> UserFull_136:
        data = obj.to_dict()
        del data["translations_disabled"]
        del data["blocked_my_stories_from"]
        del data["personal_photo"]
        del data["stories"]
        del data["stories_pinned_available"]
        del data["premium_gifts"]
        del data["voice_messages_forbidden"]
        del data["wallpaper"]
        del data["bot_broadcast_admin_rights"]
        del data["wallpaper_overridden"]
        del data["bot_group_admin_rights"]
        del data["fallback_photo"]
        return UserFull_136(**data)

    @staticmethod
    def from_140(obj: UserFull_140) -> UserFull:
        data = obj.to_dict()
        return UserFull(**data)

    @staticmethod
    def to_140(obj: UserFull) -> UserFull_140:
        data = obj.to_dict()
        del data["translations_disabled"]
        del data["blocked_my_stories_from"]
        del data["stories"]
        del data["stories_pinned_available"]
        del data["premium_gifts"]
        del data["voice_messages_forbidden"]
        del data["wallpaper"]
        del data["wallpaper_overridden"]
        del data["personal_photo"]
        del data["fallback_photo"]
        return UserFull_140(**data)

    @staticmethod
    def from_144(obj: UserFull_144) -> UserFull:
        data = obj.to_dict()
        return UserFull(**data)

    @staticmethod
    def to_144(obj: UserFull) -> UserFull_144:
        data = obj.to_dict()
        del data["translations_disabled"]
        del data["blocked_my_stories_from"]
        del data["stories"]
        del data["stories_pinned_available"]
        del data["wallpaper"]
        del data["wallpaper_overridden"]
        del data["personal_photo"]
        del data["fallback_photo"]
        return UserFull_144(**data)

    @staticmethod
    def from_151(obj: UserFull_151) -> UserFull:
        data = obj.to_dict()
        return UserFull(**data)

    @staticmethod
    def to_151(obj: UserFull) -> UserFull_151:
        data = obj.to_dict()
        del data["blocked_my_stories_from"]
        del data["stories"]
        del data["stories_pinned_available"]
        del data["wallpaper"]
        del data["wallpaper_overridden"]
        return UserFull_151(**data)

    @staticmethod
    def from_158(obj: UserFull_158) -> UserFull:
        data = obj.to_dict()
        return UserFull(**data)

    @staticmethod
    def to_158(obj: UserFull) -> UserFull_158:
        data = obj.to_dict()
        del data["stories_pinned_available"]
        del data["wallpaper_overridden"]
        del data["stories"]
        del data["blocked_my_stories_from"]
        return UserFull_158(**data)

    @staticmethod
    def from_160(obj: UserFull_160) -> UserFull:
        data = obj.to_dict()
        data["stories"] = [
            PeerStories(peer=PeerUser(user_id=story.user_id), stories=story.stories, max_read_id=story.max_read_id)
            for story in obj.stories.stories
        ]
        return UserFull(**data)

    @staticmethod
    def to_160(obj: UserFull) -> UserFull_160:
        data = obj.to_dict()
        del data["blocked_my_stories_from"]
        del data["wallpaper_overridden"]
        data["stories"] = [
            UserStories_160(user_id=story.peer.user_id, stories=story.stories, max_read_id=story.max_read_id)
            for story in obj.stories if isinstance(story.peer, PeerUser)
        ]
        return UserFull_160(**data)
