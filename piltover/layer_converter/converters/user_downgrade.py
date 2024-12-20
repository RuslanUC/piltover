from copy import copy

from piltover.layer_converter.converters.base import BaseDowngrader
from piltover.tl import User, User_136, User_160, User_148, User_145, User_166


class UserDowngradeTo136(BaseDowngrader):
    BASE_TYPE = User
    TARGET_LAYER = 136

    @classmethod
    def downgrade(cls, from_obj: User) -> User_136:
        kwargs = from_obj.to_dict()
        del kwargs["bot_attach_menu"]
        del kwargs["premium"]
        del kwargs["attach_menu_enabled"]
        del kwargs["bot_can_edit"]
        del kwargs["close_friend"]
        del kwargs["stories_hidden"]
        del kwargs["stories_unavailable"]
        del kwargs["contact_require_premium"]
        del kwargs["bot_business"]
        del kwargs["emoji_status"]
        del kwargs["usernames"]
        del kwargs["stories_max_id"]
        del kwargs["color"]
        del kwargs["profile_color"]

        return User_136(**kwargs)


class UserDowngradeTo145(BaseDowngrader):
    BASE_TYPE = User
    TARGET_LAYER = 145

    @classmethod
    def downgrade(cls, from_obj: User) -> User_145:
        kwargs = from_obj.to_dict()
        del kwargs["bot_can_edit"]
        del kwargs["close_friend"]
        del kwargs["stories_hidden"]
        del kwargs["stories_unavailable"]
        del kwargs["contact_require_premium"]
        del kwargs["bot_business"]
        del kwargs["usernames"]
        del kwargs["stories_max_id"]
        del kwargs["color"]
        del kwargs["profile_color"]

        return User_145(**kwargs)


class UserDowngradeTo148(BaseDowngrader):
    BASE_TYPE = User
    TARGET_LAYER = 148

    @classmethod
    def downgrade(cls, from_obj: User) -> User_148:
        kwargs = from_obj.to_dict()
        del kwargs["close_friend"]
        del kwargs["stories_hidden"]
        del kwargs["stories_unavailable"]
        del kwargs["contact_require_premium"]
        del kwargs["bot_business"]
        del kwargs["stories_max_id"]
        del kwargs["color"]
        del kwargs["profile_color"]

        return User_148(**kwargs)


class UserDowngradeTo160(BaseDowngrader):
    BASE_TYPE = User
    TARGET_LAYER = 160

    @classmethod
    def downgrade(cls, from_obj: User) -> User_160:
        kwargs = from_obj.to_dict()
        del kwargs["contact_require_premium"]
        del kwargs["bot_business"]
        del kwargs["color"]
        del kwargs["profile_color"]

        return User_160(**kwargs)


class UserDowngradeTo166(BaseDowngrader):
    BASE_TYPE = User
    TARGET_LAYER = 166

    @classmethod
    def downgrade(cls, from_obj: User) -> User_166:
        kwargs = from_obj.to_dict()
        del kwargs["contact_require_premium"]
        del kwargs["bot_business"]
        del kwargs["profile_color"]

        return User_166(**kwargs)


class UserDontDowngrade(BaseDowngrader):
    BASE_TYPE = User
    TARGET_LAYER = 177

    @classmethod
    def downgrade(cls, from_obj: User) -> User:
        return copy(from_obj)
