from piltover.layer_converter.converters.base import AutoDowngrader
from piltover.tl import Channel, Channel_136, Channel_148, Channel_164, Channel_166, Channel_167, Channel_186, \
    Channel_196


class ChannelDowngradeTo136(AutoDowngrader):
    BASE_TYPE = Channel
    TARGET_LAYER = 136
    TARGET_TYPE = Channel_136
    REMOVE_FIELDS = {
        "forum", "stories_hidden", "stories_hidden_min", "stories_unavailable", "usernames", "stories_max_id", "color",
        "profile_color", "emoji_status", "level", "bot_verification_icon", "send_paid_messages_stars",
        "signature_profiles", "subscription_until_date",
    }


class ChannelDowngradeTo148(AutoDowngrader):
    BASE_TYPE = Channel
    TARGET_LAYER = 148
    TARGET_TYPE = Channel_148
    REMOVE_FIELDS = {
        "stories_hidden", "stories_hidden_min", "stories_unavailable", "stories_max_id", "color", "profile_color",
        "emoji_status", "level", "bot_verification_icon", "send_paid_messages_stars", "signature_profiles",
        "subscription_until_date",
    }


class ChannelDowngradeTo164(AutoDowngrader):
    BASE_TYPE = Channel
    TARGET_LAYER = 164
    TARGET_TYPE = Channel_164
    REMOVE_FIELDS = {
        "color", "profile_color", "emoji_status", "level", "bot_verification_icon", "send_paid_messages_stars",
        "signature_profiles", "subscription_until_date",
    }


class ChannelDowngradeTo166(AutoDowngrader):
    BASE_TYPE = Channel
    TARGET_LAYER = 166
    TARGET_TYPE = Channel_166
    REMOVE_FIELDS = {
        "signature_profiles", "profile_color", "emoji_status", "level", "bot_verification_icon",
        "send_paid_messages_stars", "subscription_until_date",
    }


class ChannelDowngradeTo167(AutoDowngrader):
    BASE_TYPE = Channel
    TARGET_LAYER = 167
    TARGET_TYPE = Channel_167
    REMOVE_FIELDS = {
        "signature_profiles", "profile_color", "emoji_status", "level", "subscription_until_date",
        "bot_verification_icon", "send_paid_messages_stars",
    }


class ChannelDowngradeTo186(AutoDowngrader):
    BASE_TYPE = Channel
    TARGET_LAYER = 186
    TARGET_TYPE = Channel_186
    REMOVE_FIELDS = {"bot_verification_icon", "send_paid_messages_stars"}


class ChannelDowngradeTo196(AutoDowngrader):
    BASE_TYPE = Channel
    TARGET_LAYER = 196
    TARGET_TYPE = Channel_196
    REMOVE_FIELDS = {"send_paid_messages_stars"}


class ChannelDontDowngrade(AutoDowngrader):
    BASE_TYPE = Channel
    TARGET_LAYER = 201
    TARGET_TYPE = Channel
    REMOVE_FIELDS = set()
