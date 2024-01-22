from piltover.tl_new import User, User_166, User_160, User_148, User_145, User_136, PeerColor
from piltover.tl_new.converter import ConverterBase


class UserConverter(ConverterBase):
    base = User
    old = [User_136, User_145, User_148, User_160, User_166]
    layers = [136, 145, 148, 160, 166]

    @staticmethod
    def from_136(obj: User_136) -> User:
        return User(**obj.to_dict())

    @staticmethod
    def from_145(obj: User_145) -> User:
        return User(**obj.to_dict())

    @staticmethod
    def from_148(obj: User_148) -> User:
        return User(**obj.to_dict())

    @staticmethod
    def from_160(obj: User_160) -> User:
        return User(**obj.to_dict())

    @staticmethod
    def from_166(obj: User_166) -> User:
        data = obj.to_dict()
        data["color"] = PeerColor(color=data["color"]) if data["color"] is not None else None
        return User(**data)


    @staticmethod
    def to_136(obj: User) -> User_136:
        data = obj.to_dict()
        del data["bot_attach_menu"]
        del data["premium"]
        del data["attach_menu_enabled"]
        del data["flags2"]
        del data["bot_can_edit"]
        del data["close_friend"]
        del data["stories_hidden"]
        del data["stories_unavailable"]
        del data["emoji_status"]
        del data["usernames"]
        del data["stories_max_id"]
        del data["color"]
        del data["profile_color"]
        return User_136(**data)

    @staticmethod
    def to_145(obj: User) -> User_145:
        data = obj.to_dict()
        del data["flags2"]
        del data["bot_can_edit"]
        del data["close_friend"]
        del data["stories_hidden"]
        del data["stories_unavailable"]
        del data["usernames"]
        del data["stories_max_id"]
        del data["color"]
        del data["profile_color"]
        return User_145(**data)

    @staticmethod
    def to_148(obj: User) -> User_148:
        data = obj.to_dict()
        del data["close_friend"]
        del data["stories_hidden"]
        del data["stories_unavailable"]
        del data["stories_max_id"]
        del data["color"]
        del data["profile_color"]
        return User_148(**data)

    @staticmethod
    def to_160(obj: User) -> User_160:
        return User(**obj.to_dict())

    @staticmethod
    def to_166(obj: User) -> User_166:
        data = obj.to_dict()
        data["color"] = PeerColor(color=data["color"]) if data["color"] is not None else None
        return User(**data)
