from piltover.layer_converter.converters.base import AutoDowngrader
from piltover.tl import User, User_136, User_160, User_148, User_145, User_166


class UserDowngradeTo136(AutoDowngrader):
    BASE_TYPE = User
    TARGET_LAYER = 136
    TARGET_TYPE = User_136
    REMOVE_FIELDS = {
        "bot_attach_menu", "premium", "attach_menu_enabled", "bot_can_edit", "close_friend", "stories_hidden",
        "stories_unavailable", "contact_require_premium", "bot_business", "emoji_status", "usernames", "stories_max_id",
        "color", "profile_color",
    }


class UserDowngradeTo145(AutoDowngrader):
    BASE_TYPE = User
    TARGET_LAYER = 145
    TARGET_TYPE = User_145
    REMOVE_FIELDS = {
        "bot_can_edit", "close_friend", "stories_hidden", "stories_unavailable", "contact_require_premium",
        "bot_business", "usernames", "stories_max_id", "color", "profile_color",
    }


class UserDowngradeTo148(AutoDowngrader):
    BASE_TYPE = User
    TARGET_LAYER = 148
    TARGET_TYPE = User_148
    REMOVE_FIELDS = {
        "close_friend", "stories_hidden", "stories_unavailable", "contact_require_premium", "bot_business",
        "stories_max_id", "color", "profile_color",
    }


class UserDowngradeTo160(AutoDowngrader):
    BASE_TYPE = User
    TARGET_LAYER = 160
    TARGET_TYPE = User_160
    REMOVE_FIELDS = {
        "contact_require_premium", "bot_business", "color", "profile_color",
    }


class UserDowngradeTo166(AutoDowngrader):
    BASE_TYPE = User
    TARGET_LAYER = 166
    TARGET_TYPE = User_166
    REMOVE_FIELDS = {
        "contact_require_premium", "bot_business", "profile_color",
    }


class UserDontDowngrade(AutoDowngrader):
    BASE_TYPE = User
    TARGET_LAYER = 177
    TARGET_TYPE = User
    REMOVE_FIELDS = set()
