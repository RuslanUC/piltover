from piltover.layer_converter.converters.base import AutoDowngrader
from piltover.tl import User, User_133, User_160, User_148, User_145, User_166, User_167, User_185, User_196


class UserDowngradeTo133(AutoDowngrader):
    BASE_TYPE = User
    TARGET_TYPE = User_133
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = {
        "bot_attach_menu", "premium", "attach_menu_enabled", "bot_can_edit", "close_friend", "stories_hidden",
        "stories_unavailable", "contact_require_premium", "bot_business", "emoji_status", "usernames", "stories_max_id",
        "color", "profile_color", "bot_has_main_app", "bot_active_users", "bot_verification_icon",
        "send_paid_messages_stars",
    }


class UserDowngradeTo145(AutoDowngrader):
    BASE_TYPE = User
    TARGET_TYPE = User_145
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = {
        "bot_can_edit", "close_friend", "stories_hidden", "stories_unavailable", "contact_require_premium",
        "bot_business", "usernames", "stories_max_id", "color", "profile_color", "bot_has_main_app", "bot_active_users",
        "bot_verification_icon", "send_paid_messages_stars",
    }


class UserDowngradeTo148(AutoDowngrader):
    BASE_TYPE = User
    TARGET_TYPE = User_148
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = {
        "close_friend", "stories_hidden", "stories_unavailable", "contact_require_premium", "bot_business",
        "stories_max_id", "color", "profile_color", "bot_has_main_app", "bot_active_users", "bot_verification_icon",
        "send_paid_messages_stars",
    }


class UserDowngradeTo160(AutoDowngrader):
    BASE_TYPE = User
    TARGET_TYPE = User_160
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = {
        "contact_require_premium", "bot_business", "color", "profile_color", "bot_has_main_app", "bot_active_users",
        "bot_verification_icon", "send_paid_messages_stars",
    }


class UserDowngradeTo166(AutoDowngrader):
    BASE_TYPE = User
    TARGET_TYPE = User_166
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = {
        "contact_require_premium", "bot_business", "profile_color", "bot_has_main_app", "bot_active_users",
        "bot_verification_icon", "send_paid_messages_stars",
    }


class UserDowngradeTo167(AutoDowngrader):
    BASE_TYPE = User
    TARGET_TYPE = User_167
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = {
        "contact_require_premium", "bot_business", "bot_has_main_app", "bot_active_users", "bot_verification_icon",
        "send_paid_messages_stars",
    }


class UserDowngradeTo185(AutoDowngrader):
    BASE_TYPE = User
    TARGET_TYPE = User_185
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = {"bot_verification_icon", "send_paid_messages_stars"}


class UserDowngradeTo196(AutoDowngrader):
    BASE_TYPE = User
    TARGET_TYPE = User_196
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = {"send_paid_messages_stars"}


class UserDontDowngrade(AutoDowngrader):
    BASE_TYPE = User
    TARGET_TYPE = User
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = set()
