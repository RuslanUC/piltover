from piltover.layer_converter.converters.base import AutoDowngrader
from piltover.tl import User, User_136, User_160, User_148, User_145, User_166, User_167, User_185, User_196


class UserDowngradeTo136(AutoDowngrader):
    BASE_TYPE = User
    TARGET_LAYER = 136
    TARGET_TYPE = User_136
    REMOVE_FIELDS = {
        "bot_attach_menu", "premium", "attach_menu_enabled", "bot_can_edit", "close_friend", "stories_hidden",
        "stories_unavailable", "contact_require_premium", "bot_business", "emoji_status", "usernames", "stories_max_id",
        "color", "profile_color", "bot_has_main_app", "bot_active_users", "bot_verification_icon",
        "send_paid_messages_stars",
    }


class UserDowngradeTo145(AutoDowngrader):
    BASE_TYPE = User
    TARGET_LAYER = 145
    TARGET_TYPE = User_145
    REMOVE_FIELDS = {
        "bot_can_edit", "close_friend", "stories_hidden", "stories_unavailable", "contact_require_premium",
        "bot_business", "usernames", "stories_max_id", "color", "profile_color", "bot_has_main_app", "bot_active_users",
        "bot_verification_icon", "send_paid_messages_stars",
    }


class UserDowngradeTo148(AutoDowngrader):
    BASE_TYPE = User
    TARGET_LAYER = 148
    TARGET_TYPE = User_148
    REMOVE_FIELDS = {
        "close_friend", "stories_hidden", "stories_unavailable", "contact_require_premium", "bot_business",
        "stories_max_id", "color", "profile_color", "bot_has_main_app", "bot_active_users", "bot_verification_icon",
        "send_paid_messages_stars",
    }


class UserDowngradeTo160(AutoDowngrader):
    BASE_TYPE = User
    TARGET_LAYER = 160
    TARGET_TYPE = User_160
    REMOVE_FIELDS = {
        "contact_require_premium", "bot_business", "color", "profile_color", "bot_has_main_app", "bot_active_users",
        "bot_verification_icon", "send_paid_messages_stars",
    }


class UserDowngradeTo166(AutoDowngrader):
    BASE_TYPE = User
    TARGET_LAYER = 166
    TARGET_TYPE = User_166
    REMOVE_FIELDS = {
        "contact_require_premium", "bot_business", "profile_color", "bot_has_main_app", "bot_active_users",
        "bot_verification_icon", "send_paid_messages_stars",
    }


class UserDowngradeTo167(AutoDowngrader):
    BASE_TYPE = User
    TARGET_LAYER = 167
    TARGET_TYPE = User_167
    REMOVE_FIELDS = {
        "contact_require_premium", "bot_business", "bot_has_main_app", "bot_active_users", "bot_verification_icon",
        "send_paid_messages_stars",
    }


class UserDowngradeTo185(AutoDowngrader):
    BASE_TYPE = User
    TARGET_LAYER = 185
    TARGET_TYPE = User_185
    REMOVE_FIELDS = {"bot_verification_icon", "send_paid_messages_stars"}


class UserDowngradeTo196(AutoDowngrader):
    BASE_TYPE = User
    TARGET_LAYER = 196
    TARGET_TYPE = User_196
    REMOVE_FIELDS = {"send_paid_messages_stars"}


class UserDontDowngrade(AutoDowngrader):
    BASE_TYPE = User
    TARGET_LAYER = 201
    TARGET_TYPE = User
    REMOVE_FIELDS = set()
