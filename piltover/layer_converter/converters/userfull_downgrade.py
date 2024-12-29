from piltover.layer_converter.converters import AutoDowngrader
from piltover.tl import UserFull, UserFull_136, UserFull_140, UserFull_144, UserFull_151, UserFull_158, UserFull_160, \
    UserFull_164, UserFull_176


class UserFullDowngradeTo136(AutoDowngrader):
    BASE_TYPE = UserFull
    TARGET_LAYER = 136
    TARGET_TYPE = UserFull_136
    REMOVE_FIELDS = {
        "voice_messages_forbidden", "translations_disabled", "stories_pinned_available", "blocked_my_stories_from",
        "wallpaper_overridden", "contact_require_premium", "read_dates_private", "personal_photo", "fallback_photo",
        "bot_group_admin_rights", "bot_broadcast_admin_rights", "premium_gifts", "wallpaper", "stories",
        "business_work_hours", "business_location", "business_greeting_message", "business_away_message",
        "business_intro", "birthday", "personal_channel_id", "personal_channel_message",
    }


class UserFullDowngradeTo140(AutoDowngrader):
    BASE_TYPE = UserFull
    TARGET_LAYER = 140
    TARGET_TYPE = UserFull_140
    REMOVE_FIELDS = {
        "voice_messages_forbidden", "translations_disabled", "stories_pinned_available", "blocked_my_stories_from",
        "wallpaper_overridden", "contact_require_premium", "read_dates_private", "personal_photo", "fallback_photo",
        "premium_gifts", "wallpaper", "stories", "business_work_hours", "business_location",
        "business_greeting_message", "business_away_message", "business_intro", "birthday", "personal_channel_id",
        "personal_channel_message",
    }


class UserFullDowngradeTo144(AutoDowngrader):
    BASE_TYPE = UserFull
    TARGET_LAYER = 144
    TARGET_TYPE = UserFull_144
    REMOVE_FIELDS = {
        "translations_disabled", "stories_pinned_available", "blocked_my_stories_from", "wallpaper_overridden",
        "contact_require_premium", "read_dates_private", "personal_photo", "fallback_photo", "wallpaper", "stories",
        "business_work_hours", "business_location", "business_greeting_message", "business_away_message",
        "business_intro", "birthday", "personal_channel_id", "personal_channel_message",
    }


class UserFullDowngradeTo151(AutoDowngrader):
    BASE_TYPE = UserFull
    TARGET_LAYER = 151
    TARGET_TYPE = UserFull_151
    REMOVE_FIELDS = {
        "stories_pinned_available", "blocked_my_stories_from", "wallpaper_overridden", "contact_require_premium",
        "read_dates_private", "wallpaper", "stories", "business_work_hours", "business_location",
        "business_greeting_message", "business_away_message", "business_intro", "birthday", "personal_channel_id",
        "personal_channel_message",
    }


class UserFullDowngradeTo158(AutoDowngrader):
    BASE_TYPE = UserFull
    TARGET_LAYER = 158
    TARGET_TYPE = UserFull_158
    REMOVE_FIELDS = {
        "stories_pinned_available", "blocked_my_stories_from", "wallpaper_overridden", "contact_require_premium",
        "read_dates_private", "stories", "business_work_hours", "business_location", "business_greeting_message",
        "business_away_message", "business_intro", "birthday", "personal_channel_id", "personal_channel_message",
    }


class UserFullDowngradeTo160(AutoDowngrader):
    BASE_TYPE = UserFull
    TARGET_LAYER = 160
    TARGET_TYPE = UserFull_160
    REMOVE_FIELDS = {
        "blocked_my_stories_from", "wallpaper_overridden", "contact_require_premium", "read_dates_private",
        "business_work_hours", "business_location", "business_greeting_message", "business_away_message",
        "business_intro", "birthday", "personal_channel_id", "personal_channel_message",
    }


class UserFullDowngradeTo164(AutoDowngrader):
    BASE_TYPE = UserFull
    TARGET_LAYER = 164
    TARGET_TYPE = UserFull_164
    REMOVE_FIELDS = {
        "wallpaper_overridden", "contact_require_premium", "read_dates_private", "business_work_hours",
        "business_location", "business_greeting_message", "business_away_message", "business_intro", "birthday",
        "personal_channel_id", "personal_channel_message",
    }


class UserFullDowngradeTo176(AutoDowngrader):
    BASE_TYPE = UserFull
    TARGET_LAYER = 176
    TARGET_TYPE = UserFull_176
    REMOVE_FIELDS = {
        "business_intro", "birthday", "personal_channel_id", "personal_channel_message",
    }


class UserFullDontDowngrade(AutoDowngrader):
    BASE_TYPE = UserFull
    TARGET_LAYER = 177
    TARGET_TYPE = UserFull
    REMOVE_FIELDS = set()
