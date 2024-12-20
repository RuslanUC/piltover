from copy import copy

from piltover.layer_converter.converters.base import BaseDowngrader
from piltover.tl import UserFull, UserFull_136, UserFull_140, UserFull_144, UserFull_151, UserFull_158, UserFull_160, \
    UserFull_164, UserFull_176


class UserFullDowngradeTo136(BaseDowngrader):
    BASE_TYPE = UserFull
    TARGET_LAYER = 136

    @classmethod
    def downgrade(cls, from_obj: UserFull) -> UserFull_136:
        kwargs = from_obj.to_dict()
        del kwargs["voice_messages_forbidden"]
        del kwargs["translations_disabled"]
        del kwargs["stories_pinned_available"]
        del kwargs["blocked_my_stories_from"]
        del kwargs["wallpaper_overridden"]
        del kwargs["contact_require_premium"]
        del kwargs["read_dates_private"]
        del kwargs["personal_photo"]
        del kwargs["fallback_photo"]
        del kwargs["bot_group_admin_rights"]
        del kwargs["bot_broadcast_admin_rights"]
        del kwargs["premium_gifts"]
        del kwargs["wallpaper"]
        del kwargs["stories"]
        del kwargs["business_work_hours"]
        del kwargs["business_location"]
        del kwargs["business_greeting_message"]
        del kwargs["business_away_message"]
        del kwargs["business_intro"]
        del kwargs["birthday"]
        del kwargs["personal_channel_id"]
        del kwargs["personal_channel_message"]

        return UserFull_136(**kwargs)


class UserFullDowngradeTo140(BaseDowngrader):
    BASE_TYPE = UserFull
    TARGET_LAYER = 140

    @classmethod
    def downgrade(cls, from_obj: UserFull) -> UserFull_140:
        kwargs = from_obj.to_dict()
        del kwargs["voice_messages_forbidden"]
        del kwargs["translations_disabled"]
        del kwargs["stories_pinned_available"]
        del kwargs["blocked_my_stories_from"]
        del kwargs["wallpaper_overridden"]
        del kwargs["contact_require_premium"]
        del kwargs["read_dates_private"]
        del kwargs["personal_photo"]
        del kwargs["fallback_photo"]
        del kwargs["premium_gifts"]
        del kwargs["wallpaper"]
        del kwargs["stories"]
        del kwargs["business_work_hours"]
        del kwargs["business_location"]
        del kwargs["business_greeting_message"]
        del kwargs["business_away_message"]
        del kwargs["business_intro"]
        del kwargs["birthday"]
        del kwargs["personal_channel_id"]
        del kwargs["personal_channel_message"]

        return UserFull_140(**kwargs)


class UserFullDowngradeTo144(BaseDowngrader):
    BASE_TYPE = UserFull
    TARGET_LAYER = 144

    @classmethod
    def downgrade(cls, from_obj: UserFull) -> UserFull_144:
        kwargs = from_obj.to_dict()
        del kwargs["translations_disabled"]
        del kwargs["stories_pinned_available"]
        del kwargs["blocked_my_stories_from"]
        del kwargs["wallpaper_overridden"]
        del kwargs["contact_require_premium"]
        del kwargs["read_dates_private"]
        del kwargs["personal_photo"]
        del kwargs["fallback_photo"]
        del kwargs["wallpaper"]
        del kwargs["stories"]
        del kwargs["business_work_hours"]
        del kwargs["business_location"]
        del kwargs["business_greeting_message"]
        del kwargs["business_away_message"]
        del kwargs["business_intro"]
        del kwargs["birthday"]
        del kwargs["personal_channel_id"]
        del kwargs["personal_channel_message"]

        return UserFull_144(**kwargs)


class UserFullDowngradeTo151(BaseDowngrader):
    BASE_TYPE = UserFull
    TARGET_LAYER = 151

    @classmethod
    def downgrade(cls, from_obj: UserFull) -> UserFull_151:
        kwargs = from_obj.to_dict()
        del kwargs["stories_pinned_available"]
        del kwargs["blocked_my_stories_from"]
        del kwargs["wallpaper_overridden"]
        del kwargs["contact_require_premium"]
        del kwargs["read_dates_private"]
        del kwargs["wallpaper"]
        del kwargs["stories"]
        del kwargs["business_work_hours"]
        del kwargs["business_location"]
        del kwargs["business_greeting_message"]
        del kwargs["business_away_message"]
        del kwargs["business_intro"]
        del kwargs["birthday"]
        del kwargs["personal_channel_id"]
        del kwargs["personal_channel_message"]

        return UserFull_151(**kwargs)


class UserFullDowngradeTo158(BaseDowngrader):
    BASE_TYPE = UserFull
    TARGET_LAYER = 158

    @classmethod
    def downgrade(cls, from_obj: UserFull) -> UserFull_158:
        kwargs = from_obj.to_dict()
        del kwargs["stories_pinned_available"]
        del kwargs["blocked_my_stories_from"]
        del kwargs["wallpaper_overridden"]
        del kwargs["contact_require_premium"]
        del kwargs["read_dates_private"]
        del kwargs["stories"]
        del kwargs["business_work_hours"]
        del kwargs["business_location"]
        del kwargs["business_greeting_message"]
        del kwargs["business_away_message"]
        del kwargs["business_intro"]
        del kwargs["birthday"]
        del kwargs["personal_channel_id"]
        del kwargs["personal_channel_message"]

        return UserFull_158(**kwargs)


class UserFullDowngradeTo160(BaseDowngrader):
    BASE_TYPE = UserFull
    TARGET_LAYER = 160

    @classmethod
    def downgrade(cls, from_obj: UserFull) -> UserFull_160:
        kwargs = from_obj.to_dict()
        del kwargs["blocked_my_stories_from"]
        del kwargs["wallpaper_overridden"]
        del kwargs["contact_require_premium"]
        del kwargs["read_dates_private"]
        del kwargs["business_work_hours"]
        del kwargs["business_location"]
        del kwargs["business_greeting_message"]
        del kwargs["business_away_message"]
        del kwargs["business_intro"]
        del kwargs["birthday"]
        del kwargs["personal_channel_id"]
        del kwargs["personal_channel_message"]

        return UserFull_160(**kwargs)


class UserFullDowngradeTo164(BaseDowngrader):
    BASE_TYPE = UserFull
    TARGET_LAYER = 164

    @classmethod
    def downgrade(cls, from_obj: UserFull) -> UserFull_164:
        kwargs = from_obj.to_dict()
        del kwargs["wallpaper_overridden"]
        del kwargs["contact_require_premium"]
        del kwargs["read_dates_private"]
        del kwargs["business_work_hours"]
        del kwargs["business_location"]
        del kwargs["business_greeting_message"]
        del kwargs["business_away_message"]
        del kwargs["business_intro"]
        del kwargs["birthday"]
        del kwargs["personal_channel_id"]
        del kwargs["personal_channel_message"]

        return UserFull_164(**kwargs)


class UserFullDowngradeTo176(BaseDowngrader):
    BASE_TYPE = UserFull
    TARGET_LAYER = 176

    @classmethod
    def downgrade(cls, from_obj: UserFull) -> UserFull_176:
        kwargs = from_obj.to_dict()
        del kwargs["business_intro"]
        del kwargs["birthday"]
        del kwargs["personal_channel_id"]
        del kwargs["personal_channel_message"]

        return UserFull_176(**kwargs)


class UserFullDontDowngrade(BaseDowngrader):
    BASE_TYPE = UserFull
    TARGET_LAYER = 177

    @classmethod
    def downgrade(cls, from_obj: UserFull) -> UserFull:
        return copy(from_obj)
