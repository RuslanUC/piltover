from piltover.layer_converter.converters.base import AutoDowngrader
from piltover.tl import ChannelFull_136, ChannelFull, ChannelFull_140, ChannelFull_145, ChannelFull_164, ChannelFull_168



class ChannelFullDowngradeTo136(AutoDowngrader):
    BASE_TYPE = ChannelFull
    TARGET_LAYER = 136
    TARGET_TYPE = ChannelFull_136
    REMOVE_FIELDS = {
        "can_delete_channel", "antispam", "participants_hidden", "translations_disabled", "stories_pinned_available",
        "view_forum_as_messages", "restricted_sponsored", "can_view_revenue", "stories", "wallpaper", "boosts_applied",
        "boosts_unrestrict", "emojiset",
    }


class ChannelFullDowngradeTo140(AutoDowngrader):
    BASE_TYPE = ChannelFull
    TARGET_LAYER = 140
    TARGET_TYPE = ChannelFull_140
    REMOVE_FIELDS = {
        "antispam", "participants_hidden", "translations_disabled", "stories_pinned_available",
        "view_forum_as_messages", "restricted_sponsored", "can_view_revenue", "stories", "wallpaper", "boosts_applied",
        "boosts_unrestrict", "emojiset",
    }


class ChannelFullDowngradeTo145(AutoDowngrader):
    BASE_TYPE = ChannelFull
    TARGET_LAYER = 145
    TARGET_TYPE = ChannelFull_145
    REMOVE_FIELDS = {
        "antispam", "participants_hidden", "translations_disabled", "stories_pinned_available",
        "view_forum_as_messages", "restricted_sponsored", "can_view_revenue", "stories", "wallpaper", "boosts_applied",
        "boosts_unrestrict", "emojiset",
    }


class ChannelFullDowngradeTo164(AutoDowngrader):
    BASE_TYPE = ChannelFull
    TARGET_LAYER = 164
    TARGET_TYPE = ChannelFull_164
    REMOVE_FIELDS = {
        "view_forum_as_messages", "restricted_sponsored", "can_view_revenue", "wallpaper", "boosts_applied",
        "boosts_unrestrict", "emojiset",
    }


class ChannelFullDowngradeTo168(AutoDowngrader):
    BASE_TYPE = ChannelFull
    TARGET_LAYER = 168
    TARGET_TYPE = ChannelFull_168
    REMOVE_FIELDS = {
        "restricted_sponsored", "can_view_revenue", "boosts_applied", "boosts_unrestrict", "emojiset",
    }


class ChannelFullDontDowngrade(AutoDowngrader):
    BASE_TYPE = ChannelFull
    TARGET_LAYER = 177
    TARGET_TYPE = ChannelFull
    REMOVE_FIELDS = set()
