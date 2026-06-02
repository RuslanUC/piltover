from piltover.layer_converter.converters import AutoDowngrader
from piltover.tl import UserFull, UserFull_135, UserFull_140, UserFull_144, UserFull_151, UserFull_158, \
    UserFull_160, UserFull_164, UserFull_176, UserFull_177, UserFull_189, UserFull_195, UserFull_196, UserFull_200


# TODO: add downgrader for UserFull_133. Cant be added right now since UserFull_135+ dont have `user` field


class UserFullDowngradeTo135(AutoDowngrader):
    BASE_TYPE = UserFull
    TARGET_TYPE = UserFull_135
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = {
        "voice_messages_forbidden", "translations_disabled", "stories_pinned_available", "blocked_my_stories_from",
        "wallpaper_overridden", "contact_require_premium", "read_dates_private", "personal_photo", "fallback_photo",
        "bot_group_admin_rights", "bot_broadcast_admin_rights", "premium_gifts", "wallpaper", "stories",
        "business_work_hours", "business_location", "business_greeting_message", "business_away_message",
        "business_intro", "birthday", "personal_channel_id", "personal_channel_message", "sponsored_enabled",
        "can_view_revenue", "bot_can_manage_emoji_status", "stargifts_count", "starref_program", "bot_verification",
        "send_paid_messages_stars", "display_gifts_button", "disallowed_gifts",
    }


class UserFullDowngradeTo140(AutoDowngrader):
    BASE_TYPE = UserFull
    TARGET_TYPE = UserFull_140
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = {
        "voice_messages_forbidden", "translations_disabled", "stories_pinned_available", "blocked_my_stories_from",
        "wallpaper_overridden", "contact_require_premium", "read_dates_private", "personal_photo", "fallback_photo",
        "premium_gifts", "wallpaper", "stories", "business_work_hours", "business_location",
        "business_greeting_message", "business_away_message", "business_intro", "birthday", "personal_channel_id",
        "personal_channel_message", "sponsored_enabled", "can_view_revenue", "bot_can_manage_emoji_status",
        "stargifts_count", "starref_program", "bot_verification", "send_paid_messages_stars", "display_gifts_button",
        "disallowed_gifts",
    }


class UserFullDowngradeTo144(AutoDowngrader):
    BASE_TYPE = UserFull
    TARGET_TYPE = UserFull_144
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = {
        "translations_disabled", "stories_pinned_available", "blocked_my_stories_from", "wallpaper_overridden",
        "contact_require_premium", "read_dates_private", "personal_photo", "fallback_photo", "wallpaper", "stories",
        "business_work_hours", "business_location", "business_greeting_message", "business_away_message",
        "business_intro", "birthday", "personal_channel_id", "personal_channel_message", "sponsored_enabled",
        "can_view_revenue", "bot_can_manage_emoji_status", "stargifts_count", "starref_program", "bot_verification",
        "send_paid_messages_stars", "display_gifts_button", "disallowed_gifts",
    }


class UserFullDowngradeTo151(AutoDowngrader):
    BASE_TYPE = UserFull
    TARGET_TYPE = UserFull_151
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = {
        "stories_pinned_available", "blocked_my_stories_from", "wallpaper_overridden", "contact_require_premium",
        "read_dates_private", "wallpaper", "stories", "business_work_hours", "business_location",
        "business_greeting_message", "business_away_message", "business_intro", "birthday", "personal_channel_id",
        "personal_channel_message", "sponsored_enabled", "can_view_revenue", "bot_can_manage_emoji_status",
        "stargifts_count", "starref_program", "bot_verification", "send_paid_messages_stars", "display_gifts_button",
        "disallowed_gifts",
    }


class UserFullDowngradeTo158(AutoDowngrader):
    BASE_TYPE = UserFull
    TARGET_TYPE = UserFull_158
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = {
        "stories_pinned_available", "blocked_my_stories_from", "wallpaper_overridden", "contact_require_premium",
        "read_dates_private", "stories", "business_work_hours", "business_location", "business_greeting_message",
        "business_away_message", "business_intro", "birthday", "personal_channel_id", "personal_channel_message",
        "sponsored_enabled", "can_view_revenue", "bot_can_manage_emoji_status", "stargifts_count", "starref_program",
        "bot_verification", "send_paid_messages_stars", "display_gifts_button", "disallowed_gifts",
    }


class UserFullDowngradeTo160(AutoDowngrader):
    BASE_TYPE = UserFull
    TARGET_TYPE = UserFull_160
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = {
        "blocked_my_stories_from", "wallpaper_overridden", "contact_require_premium", "read_dates_private",
        "business_work_hours", "business_location", "business_greeting_message", "business_away_message",
        "business_intro", "birthday", "personal_channel_id", "personal_channel_message", "sponsored_enabled",
        "can_view_revenue", "bot_can_manage_emoji_status", "stargifts_count", "starref_program", "bot_verification",
        "send_paid_messages_stars", "display_gifts_button", "disallowed_gifts",
    }


class UserFullDowngradeTo164(AutoDowngrader):
    BASE_TYPE = UserFull
    TARGET_TYPE = UserFull_164
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = {
        "wallpaper_overridden", "contact_require_premium", "read_dates_private", "business_work_hours",
        "business_location", "business_greeting_message", "business_away_message", "business_intro", "birthday",
        "personal_channel_id", "personal_channel_message", "sponsored_enabled", "can_view_revenue",
        "bot_can_manage_emoji_status", "stargifts_count", "starref_program", "bot_verification",
        "send_paid_messages_stars", "display_gifts_button", "disallowed_gifts",
    }


class UserFullDowngradeTo176(AutoDowngrader):
    BASE_TYPE = UserFull
    TARGET_TYPE = UserFull_176
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = {
        "business_intro", "birthday", "personal_channel_id", "personal_channel_message", "sponsored_enabled",
        "can_view_revenue", "bot_can_manage_emoji_status", "stargifts_count", "starref_program", "bot_verification",
        "send_paid_messages_stars", "display_gifts_button", "disallowed_gifts",
    }


class UserFullDowngradeTo177(AutoDowngrader):
    BASE_TYPE = UserFull
    TARGET_TYPE = UserFull_177
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = {
        "sponsored_enabled", "can_view_revenue", "bot_can_manage_emoji_status", "stargifts_count", "starref_program",
        "bot_verification", "send_paid_messages_stars", "display_gifts_button", "disallowed_gifts",
    }


class UserFullDowngradeTo189(AutoDowngrader):
    BASE_TYPE = UserFull
    TARGET_TYPE = UserFull_189
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = {
        "can_view_revenue", "bot_can_manage_emoji_status", "starref_program", "bot_verification",
        "send_paid_messages_stars", "display_gifts_button", "disallowed_gifts",
    }


class UserFullDowngradeTo195(AutoDowngrader):
    BASE_TYPE = UserFull
    TARGET_TYPE = UserFull_195
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = {"bot_verification", "send_paid_messages_stars", "display_gifts_button", "disallowed_gifts"}


class UserFullDowngradeTo196(AutoDowngrader):
    BASE_TYPE = UserFull
    TARGET_TYPE = UserFull_196
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = {"send_paid_messages_stars", "display_gifts_button", "disallowed_gifts"}


class UserFullDowngradeTo200(AutoDowngrader):
    BASE_TYPE = UserFull
    TARGET_TYPE = UserFull_200
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = {"display_gifts_button", "disallowed_gifts"}


class UserFullDontDowngrade(AutoDowngrader):
    BASE_TYPE = UserFull
    TARGET_TYPE = UserFull
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = set()
