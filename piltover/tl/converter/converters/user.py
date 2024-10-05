from piltover.tl import PeerColor
from piltover.tl.converter import ConverterBase
from piltover.tl.types import User, User_136, User_145, User_148, User_160, User_166


class UserConverter(ConverterBase):
    base = User
    old = [User_136, User_145, User_148, User_160, User_166]
    layers = [136, 145, 148, 160, 166]

    @staticmethod
    def from_136(obj: User_136) -> User:
        data = obj.to_dict()
        return User(**data)

    @staticmethod
    def to_136(obj: User) -> User_136:
        data = obj.to_dict()
        del data["bot_can_edit"]
        del data["attach_menu_enabled"]
        del data["bot_attach_menu"]
        del data["stories_max_id"]
        del data["stories_hidden"]
        del data["emoji_status"]
        del data["flags2"]
        del data["color"]
        del data["close_friend"]
        del data["premium"]
        del data["profile_color"]
        del data["stories_unavailable"]
        del data["usernames"]
        return User_136(**data)

    @staticmethod
    def from_145(obj: User_145) -> User:
        data = obj.to_dict()
        return User(**data)

    @staticmethod
    def to_145(obj: User) -> User_145:
        data = obj.to_dict()
        del data["bot_can_edit"]
        del data["stories_max_id"]
        del data["stories_hidden"]
        del data["flags2"]
        del data["color"]
        del data["close_friend"]
        del data["profile_color"]
        del data["stories_unavailable"]
        del data["usernames"]
        return User_145(**data)

    @staticmethod
    def from_148(obj: User_148) -> User:
        data = obj.to_dict()
        return User(**data)

    @staticmethod
    def to_148(obj: User) -> User_148:
        data = obj.to_dict()
        del data["stories_max_id"]
        del data["stories_hidden"]
        del data["color"]
        del data["close_friend"]
        del data["profile_color"]
        del data["stories_unavailable"]
        return User_148(**data)

    @staticmethod
    def from_160(obj: User_160) -> User:
        data = obj.to_dict()
        return User(**data)

    @staticmethod
    def to_160(obj: User) -> User_160:
        data = obj.to_dict()
        del data["profile_color"]
        del data["color"]
        return User_160(**data)

    @staticmethod
    def from_166(obj: User_166) -> User:
        data = obj.to_dict()
        del data["background_emoji_id"]
        if data["color"] is not None:
            data["color"] = PeerColor(color=obj.color, background_emoji_id=obj.background_emoji_id)
        return User(**data)

    @staticmethod
    def to_166(obj: User) -> User_166:
        data = obj.to_dict()
        del data["profile_color"]
        if data["color"] is not None:
            data["color"] = obj.color.color
            data["background_emoji_id"] = obj.color.background_emoji_id
        return User_166(**data)
