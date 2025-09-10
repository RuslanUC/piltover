from piltover.layer_converter.converters.base import AutoDowngrader
from piltover.tl import ChannelFull_136, ChannelFull, ChannelFull_140, ChannelFull_145, ChannelFull_164, \
    ChannelFull_168, ChannelFull_174, ChannelFull_179, ChannelFull_196, ChannelFull_133, ChannelFull_134, \
    ChannelFull_135


class ChannelFullDowngradeTo133(AutoDowngrader):
    BASE_TYPE = ChannelFull
    TARGET_LAYER = 133
    TARGET_TYPE = ChannelFull_133
    REMOVE_FIELDS = {
        "can_delete_channel", "antispam", "participants_hidden", "translations_disabled", "stories_pinned_available",
        "view_forum_as_messages", "restricted_sponsored", "can_view_revenue", "paid_media_allowed",
        "can_view_stars_revenue", "paid_reactions_available", "stargifts_available", "paid_messages_available",
        "requests_pending", "recent_requesters", "default_send_as", "available_reactions", "reactions_limit", "stories",
        "wallpaper", "boosts_applied", "boosts_unrestrict", "emojiset", "bot_verification", "stargifts_count",
    }


class ChannelFullDowngradeTo134(AutoDowngrader):
    BASE_TYPE = ChannelFull
    TARGET_LAYER = 134
    TARGET_TYPE = ChannelFull_134
    REMOVE_FIELDS = {
        "can_delete_channel", "antispam", "participants_hidden", "translations_disabled", "stories_pinned_available",
        "view_forum_as_messages", "restricted_sponsored", "can_view_revenue", "paid_media_allowed",
        "can_view_stars_revenue", "paid_reactions_available", "stargifts_available", "paid_messages_available",
        "default_send_as", "available_reactions", "reactions_limit", "stories", "wallpaper", "boosts_applied",
        "boosts_unrestrict", "emojiset", "bot_verification", "stargifts_count",
    }


class ChannelFullDowngradeTo135(AutoDowngrader):
    BASE_TYPE = ChannelFull
    TARGET_LAYER = 135
    TARGET_TYPE = ChannelFull_135
    REMOVE_FIELDS = {
        "can_delete_channel", "antispam", "participants_hidden", "translations_disabled", "stories_pinned_available",
        "view_forum_as_messages", "restricted_sponsored", "can_view_revenue", "paid_media_allowed",
        "can_view_stars_revenue", "paid_reactions_available", "stargifts_available", "paid_messages_available",
        "available_reactions", "reactions_limit", "stories", "wallpaper", "boosts_applied", "boosts_unrestrict",
        "emojiset", "bot_verification", "stargifts_count",
    }


class ChannelFullDowngradeTo136(AutoDowngrader):
    BASE_TYPE = ChannelFull
    TARGET_LAYER = 136
    TARGET_TYPE = ChannelFull_136
    REMOVE_FIELDS = {
        "can_delete_channel", "antispam", "participants_hidden", "translations_disabled", "stories_pinned_available",
        "view_forum_as_messages", "restricted_sponsored", "can_view_revenue", "stories", "wallpaper", "boosts_applied",
        "boosts_unrestrict", "emojiset", "paid_media_allowed", "can_view_stars_revenue",
        "paid_reactions_available", "stargifts_available", "paid_messages_available", "reactions_limit",
        "bot_verification", "stargifts_count",
    }


class ChannelFullDowngradeTo140(AutoDowngrader):
    BASE_TYPE = ChannelFull
    TARGET_LAYER = 140
    TARGET_TYPE = ChannelFull_140
    REMOVE_FIELDS = {
        "antispam", "participants_hidden", "translations_disabled", "stories_pinned_available",
        "view_forum_as_messages", "restricted_sponsored", "can_view_revenue", "stories", "wallpaper", "boosts_applied",
        "boosts_unrestrict", "emojiset", "paid_media_allowed", "can_view_stars_revenue",
        "paid_reactions_available", "stargifts_available", "paid_messages_available", "reactions_limit",
        "bot_verification", "stargifts_count",
    }


class ChannelFullDowngradeTo145(AutoDowngrader):
    BASE_TYPE = ChannelFull
    TARGET_LAYER = 145
    TARGET_TYPE = ChannelFull_145
    REMOVE_FIELDS = {
        "antispam", "participants_hidden", "translations_disabled", "stories_pinned_available",
        "view_forum_as_messages", "restricted_sponsored", "can_view_revenue", "stories", "wallpaper", "boosts_applied",
        "boosts_unrestrict", "emojiset", "paid_media_allowed", "can_view_stars_revenue",
        "paid_reactions_available", "stargifts_available", "paid_messages_available", "reactions_limit",
        "bot_verification", "stargifts_count",
    }


class ChannelFullDowngradeTo164(AutoDowngrader):
    BASE_TYPE = ChannelFull
    TARGET_LAYER = 164
    TARGET_TYPE = ChannelFull_164
    REMOVE_FIELDS = {
        "view_forum_as_messages", "restricted_sponsored", "can_view_revenue", "wallpaper", "boosts_applied",
        "boosts_unrestrict", "emojiset", "paid_media_allowed", "can_view_stars_revenue",
        "paid_reactions_available", "stargifts_available", "paid_messages_available", "reactions_limit",
        "bot_verification", "stargifts_count",
    }


class ChannelFullDowngradeTo168(AutoDowngrader):
    BASE_TYPE = ChannelFull
    TARGET_LAYER = 168
    TARGET_TYPE = ChannelFull_168
    REMOVE_FIELDS = {
        "restricted_sponsored", "can_view_revenue", "boosts_applied", "boosts_unrestrict", "emojiset",
        "paid_media_allowed", "can_view_stars_revenue", "paid_reactions_available", "stargifts_available",
        "paid_messages_available", "reactions_limit", "bot_verification", "stargifts_count",
    }


class ChannelFullDowngradeTo174(AutoDowngrader):
    BASE_TYPE = ChannelFull
    TARGET_LAYER = 174
    TARGET_TYPE = ChannelFull_174
    REMOVE_FIELDS = {
        "restricted_sponsored", "can_view_revenue", "paid_media_allowed", "can_view_stars_revenue",
        "paid_reactions_available", "stargifts_available", "paid_messages_available", "reactions_limit",
        "bot_verification", "stargifts_count",
    }


class ChannelFullDowngradeTo179(AutoDowngrader):
    BASE_TYPE = ChannelFull
    TARGET_LAYER = 179
    TARGET_TYPE = ChannelFull_179
    REMOVE_FIELDS = {
        "paid_media_allowed", "can_view_stars_revenue", "paid_reactions_available", "stargifts_available",
        "paid_messages_available", "bot_verification", "stargifts_count",
    }


class ChannelFullDowngradeTo196(AutoDowngrader):
    BASE_TYPE = ChannelFull
    TARGET_LAYER = 196
    TARGET_TYPE = ChannelFull_196
    REMOVE_FIELDS = {
        "stargifts_available", "paid_messages_available", "stargifts_count",
    }


class ChannelFullDontDowngrade(AutoDowngrader):
    BASE_TYPE = ChannelFull
    TARGET_LAYER = 201
    TARGET_TYPE = ChannelFull
    REMOVE_FIELDS = set()
