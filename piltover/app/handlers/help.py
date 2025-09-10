import ctypes
from time import time

from piltover.app_config import AppConfig
from piltover.db.models import AuthCountry, User, Reaction, UserReactionsSettings
from piltover.enums import ReqHandlerFlags
from piltover.tl import Config, DcOption, NearestDc, JsonObject, PremiumSubscriptionOption, JsonNumber, JsonObjectValue, \
    JsonBool, JsonArray, JsonString, ReactionEmoji
from piltover.tl.functions.help import GetConfig, GetAppConfig, GetNearestDc, GetCountriesList, \
    GetTermsOfServiceUpdate, GetPromoData, GetPremiumPromo, SaveAppLog, GetInviteText, GetPeerColors, \
    GetPeerProfileColors, DismissSuggestion
from piltover.tl.types.help import CountriesList, PromoDataEmpty, PremiumPromo, InviteText, TermsOfServiceUpdateEmpty, \
    PeerColors, PeerColorOption, AppConfig as TLAppConfig, CountriesListNotModified, AppConfigNotModified
from piltover.worker import MessageHandler

handler = MessageHandler("help")
CACHED_COUNTRIES_LIST: tuple[CountriesList | None, int] = (None, 0)


@handler.on_request(GetConfig, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_config(user: User | None):
    if user is None:
        default_reaction = None
    else:
        settings = await UserReactionsSettings.get_or_none(user=user).select_related("default_reaction")
        if settings is None:
            default_reaction = await Reaction.get_or_none(reaction="❤")
            await UserReactionsSettings.create(user=user, default_reaction=default_reaction)
        elif settings.default_reaction_id is None:
            default_reaction = await Reaction.get_or_none(reaction="❤")
            if default_reaction is not None:
                settings.default_reaction = default_reaction
                await settings.save(update_fields=["default_reaction_id"])
        else:
            default_reaction = settings.default_reaction

    return Config(
        date=int(time()),
        # This seems to be hardcoded to 1 hour on some clients, and changing it breaks them
        expires=int(time() + 60 * 60),
        this_dc=AppConfig.THIS_DC_ID,
        test_mode=False,
        dc_options=[
            DcOption(this_port_only=True, id=dc["dc_id"], ip_address=address["ip"], port=address["port"])
            for dc in AppConfig.DCS for address in dc["addresses"]
        ],
        dc_txt_domain_name="_",
        chat_size_max=AppConfig.BASIC_GROUP_MEMBER_LIMIT,  # Telegram default is 200
        megagroup_size_max=AppConfig.SUPER_GROUP_MEMBER_LIMIT,  # Telegram default is 200000
        forwarded_count_max=100,  # Telegram default is 100
        online_update_period_ms=30_000,  # Telegram default is 210000
        offline_blur_timeout_ms=30_000,  # Telegram default is 5000
        offline_idle_timeout_ms=30_000,  # Telegram default is 30000
        online_cloud_timeout_ms=30_000,  # Telegram default is 300000
        notify_cloud_delay_ms=60_000,  # Telegram default is 30000
        notify_default_delay_ms=10_000,  # Telegram default is 1500
        push_chat_period_ms=1_000,  # Telegram default is 60000
        push_chat_limit=1,
        edit_time_limit=AppConfig.EDIT_TIME_LIMIT,  # Telegram default is 172800
        revoke_time_limit=int(2 ** 31 - 1),
        revoke_pm_time_limit=int(2 ** 31 - 1),
        rating_e_decay=2,
        stickers_recent_limit=15,
        channels_read_media_period=24 * 60 * 60,
        call_receive_timeout_ms=20_000,
        call_ring_timeout_ms=20_000,
        call_connect_timeout_ms=20_000,
        call_packet_timeout_ms=5_000,
        me_url_prefix="https://127.0.0.1/",
        caption_length_max=AppConfig.MAX_CAPTION_LENGTH,  # Telegram default is 1024
        message_length_max=AppConfig.MAX_MESSAGE_LENGTH,
        webfile_dc_id=AppConfig.THIS_DC_ID,
        preload_featured_stickers=False,
        revoke_pm_inbox=True,
        reactions_default=ReactionEmoji(emoticon=default_reaction.reaction) if default_reaction is not None else None,
    )


@handler.on_request(GetNearestDc, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_nearest_dc():  # pragma: no cover
    return NearestDc(
        country="US",
        this_dc=AppConfig.THIS_DC_ID,
        nearest_dc=AppConfig.THIS_DC_ID,
    )


APP_CONFIG_HASH = int(time())
APP_CONFIG = JsonObject(value=[
    JsonObjectValue(key="about_length_limit_default", value=JsonNumber(value=float(AppConfig.MAX_USER_ABOUT_LENGTH))),
    JsonObjectValue(key="about_length_limit_premium", value=JsonNumber(value=float(AppConfig.MAX_USER_ABOUT_LENGTH))),
    JsonObjectValue(key="authorization_autoconfirm_period", value=JsonNumber(value=7 * 24 * 60 * 60.0)),
    JsonObjectValue(key="autoarchive_setting_available", value=JsonBool(value=False)),
    JsonObjectValue(key="autologin_domains", value=JsonArray(value=[])),
    JsonObjectValue(key="background_connection", value=JsonBool(value=True)),
    JsonObjectValue(key="boosts_channel_level_max", value=JsonNumber(value=100.0)),
    JsonObjectValue(key="boosts_per_sent_gift", value=JsonNumber(value=3.0)),
    JsonObjectValue(key="bot_preview_medias_max", value=JsonNumber(value=12.0)),
    JsonObjectValue(key="business_chat_links_limit", value=JsonNumber(value=100.0)),
    JsonObjectValue(key="business_promo_order", value=JsonArray(value=[])),
    JsonObjectValue(key="can_edit_factcheck", value=JsonBool(value=False)),
    JsonObjectValue(key="caption_length_limit_default", value=JsonNumber(value=float(AppConfig.MAX_CAPTION_LENGTH))),
    JsonObjectValue(key="caption_length_limit_premium", value=JsonNumber(value=float(AppConfig.MAX_CAPTION_LENGTH))),
    JsonObjectValue(key="channel_bg_icon_level_min", value=JsonNumber(value=4.0)),
    JsonObjectValue(key="channel_custom_wallpaper_level_min", value=JsonNumber(value=10.0)),
    JsonObjectValue(key="channel_emoji_status_level_min", value=JsonNumber(value=8.0)),
    JsonObjectValue(key="channel_profile_bg_icon_level_min", value=JsonNumber(value=7.0)),
    JsonObjectValue(key="channel_restrict_sponsored_level_min", value=JsonNumber(value=50.0)),
    JsonObjectValue(key="channel_revenue_withdrawal_enabled", value=JsonBool(value=True)),
    JsonObjectValue(key="channel_wallpaper_level_min", value=JsonNumber(value=9.0)),
    JsonObjectValue(key="channels_limit_default", value=JsonNumber(value=float(AppConfig.CHANNELS_PER_USER_LIMIT))),
    JsonObjectValue(key="channels_limit_premium", value=JsonNumber(value=float(AppConfig.CHANNELS_PER_USER_LIMIT))),
    JsonObjectValue(key="channels_public_limit_default", value=JsonNumber(value=float(AppConfig.PUBLIC_CHANNELS_LIMIT))),
    JsonObjectValue(key="channels_public_limit_premium", value=JsonNumber(value=float(AppConfig.PUBLIC_CHANNELS_LIMIT))),
    JsonObjectValue(key="chat_read_mark_expire_period", value=JsonNumber(value=7 * 24 * 60 * 60.0)),
    JsonObjectValue(key="chat_read_mark_size_threshold", value=JsonNumber(value=100.0)),
    JsonObjectValue(key="chatlist_invites_limit_default", value=JsonNumber(value=3.0)),
    JsonObjectValue(key="chatlist_invites_limit_premium", value=JsonNumber(value=100.0)),
    JsonObjectValue(key="chatlist_update_period", value=JsonNumber(value=300.0)),
    JsonObjectValue(key="chatlists_joined_limit_default", value=JsonNumber(value=2.0)),
    JsonObjectValue(key="chatlists_joined_limit_premium", value=JsonNumber(value=20.0)),
    # JsonObjectValue(key="default_emoji_statuses_stickerset_id", value=JsonString(value="773947703670341676")),
    JsonObjectValue(key="dialog_filters_chats_limit_default", value=JsonNumber(value=100.0)),
    JsonObjectValue(key="dialog_filters_chats_limit_premium", value=JsonNumber(value=200.0)),
    JsonObjectValue(key="dialog_filters_enabled", value=JsonBool(value=True)),
    JsonObjectValue(key="dialog_filters_limit_default", value=JsonNumber(value=10.0)),
    JsonObjectValue(key="dialog_filters_limit_premium", value=JsonNumber(value=30.0)),
    JsonObjectValue(key="dialog_filters_tooltip", value=JsonBool(value=False)),
    JsonObjectValue(key="dialogs_folder_pinned_limit_default", value=JsonNumber(value=100.0)),
    JsonObjectValue(key="dialogs_folder_pinned_limit_premium", value=JsonNumber(value=200.0)),
    JsonObjectValue(key="dialogs_pinned_limit_default", value=JsonNumber(value=float(AppConfig.PINNED_DIALOGS_LIMIT))),
    JsonObjectValue(key="dialogs_pinned_limit_premium", value=JsonNumber(value=float(AppConfig.PINNED_DIALOGS_LIMIT))),
    JsonObjectValue(key="dismissed_suggestions", value=JsonArray(value=[
        JsonString(value="AUTOARCHIVE_POPULAR"),
        JsonString(value="NEWCOMER_TICKS"),
        JsonString(value="PREMIUM_ANNUAL"),
        JsonString(value="PREMIUM_UPGRADE"),
        JsonString(value="PREMIUM_RESTORE"),
        JsonString(value="PREMIUM_CHRISTMAS"),
        JsonString(value="PREMIUM_GRACE"),
        JsonString(value="BIRTHDAY_SETUP"),
        JsonString(value="STARS_SUBSCRIPTION_LOW_BALANCE"),
        JsonString(value="USERPIC_SETUP"),
        JsonString(value="BIRTHDAY_CONTACTS_TODAY"),
        JsonString(value="CONVERT_GIGAGROUP"),
    ])),
    JsonObjectValue(key="emojies_animated_zoom", value=JsonNumber(value=0.625)),
    JsonObjectValue(key="emojies_send_dice", value=JsonArray(value=[
        JsonString(value="\U0001F3B2"),
        JsonString(value="\U0001F3AF"),
        JsonString(value="\U0001F3C0"),
        JsonString(value="\u26bd"),
        JsonString(value="\u26bd\ufe0f"),
        JsonString(value="\U0001F3B0"),
        JsonString(value="\U0001F3B3"),
    ])),
    JsonObjectValue(key="emojies_send_dice_success", value=JsonObject(value=[
        JsonObjectValue(key="\U0001F3AF", value=JsonObject(value=[
            JsonObjectValue(key="value", value=JsonNumber(value=6.0)),
            JsonObjectValue(key="frame_start", value=JsonNumber(value=62.0)),
        ])),
        JsonObjectValue(key="\U0001F3C0", value=JsonObject(value=[
            JsonObjectValue(key="value", value=JsonNumber(value=5.0)),
            JsonObjectValue(key="frame_start", value=JsonNumber(value=110.0)),
        ])),
        JsonObjectValue(key="\u26bd", value=JsonObject(value=[
            JsonObjectValue(key="value", value=JsonNumber(value=5.0)),
            JsonObjectValue(key="frame_start", value=JsonNumber(value=110.0)),
        ])),
        JsonObjectValue(key="\u26bd\ufe0f", value=JsonObject(value=[
            JsonObjectValue(key="value", value=JsonNumber(value=5.0)),
            JsonObjectValue(key="frame_start", value=JsonNumber(value=110.0)),
        ])),
        JsonObjectValue(key="\U0001F3B0", value=JsonObject(value=[
            JsonObjectValue(key="value", value=JsonNumber(value=64.0)),
            JsonObjectValue(key="frame_start", value=JsonNumber(value=110.0)),
        ])),
        JsonObjectValue(key="\U0001F3B3", value=JsonObject(value=[
            JsonObjectValue(key="value", value=JsonNumber(value=6.0)),
            JsonObjectValue(key="frame_start", value=JsonNumber(value=110.0)),
        ])),
    ])),
    JsonObjectValue(key="emojies_sounds", value=JsonArray(value=[])),
    JsonObjectValue(key="factcheck_length_limit", value=JsonNumber(value=1024.0)),
    JsonObjectValue(key="fragment_prefixes", value=JsonArray(value=[JsonString(value="888")])),
    JsonObjectValue(key="gif_search_branding", value=JsonString(value="tenor")),
    JsonObjectValue(key="gif_search_emojies", value=JsonArray(value=[
        JsonString(value="\U0001F44D"),
        JsonString(value="\U0001F618"),
        JsonString(value="\U0001F60D"),
        JsonString(value="\U0001F621"),
        JsonString(value="\U0001F973"),
        JsonString(value="\U0001F602"),
        JsonString(value="\U0001F62E"),
        JsonString(value="\U0001F644"),
        JsonString(value="\U0001F60E"),
        JsonString(value="\U0001F44E")
    ])),
    JsonObjectValue(key="giveaway_add_peers_max", value=JsonNumber(value=10.0)),
    JsonObjectValue(key="giveaway_boosts_per_premium", value=JsonNumber(value=4.0)),
    JsonObjectValue(key="giveaway_countries_max", value=JsonNumber(value=10.0)),
    JsonObjectValue(key="giveaway_gifts_purchase_available", value=JsonBool(value=False)),
    JsonObjectValue(key="giveaway_period_max", value=JsonNumber(value=2678400.0)),
    JsonObjectValue(key="group_custom_wallpaper_level_min", value=JsonNumber(value=10.0)),
    JsonObjectValue(key="group_emoji_status_level_min", value=JsonNumber(value=8.0)),
    JsonObjectValue(key="group_emoji_stickers_level_min", value=JsonNumber(value=4.0)),
    JsonObjectValue(key="group_profile_bg_icon_level_min", value=JsonNumber(value=5.0)),
    JsonObjectValue(key="group_transcribe_level_min", value=JsonNumber(value=6.0)),
    JsonObjectValue(key="group_wallpaper_level_min", value=JsonNumber(value=9.0)),
    JsonObjectValue(key="groupcall_video_participants_max", value=JsonNumber(value=1000.0)),
    JsonObjectValue(key="hidden_members_group_size_min", value=JsonNumber(value=100.0)),
    JsonObjectValue(key="ignore_restriction_reasons", value=JsonArray(value=[])),
    JsonObjectValue(key="inapp_update_check_delay", value=JsonNumber(value=365 * 24 * 60 * 60.0)),
    JsonObjectValue(key="intro_description_length_limit", value=JsonNumber(value=70.0)),
    JsonObjectValue(key="intro_title_length_limit", value=JsonNumber(value=32.0)),
    JsonObjectValue(key="keep_alive_service", value=JsonBool(value=True)),
    JsonObjectValue(key="large_queue_max_active_operations_count", value=JsonNumber(value=2.0)),
    JsonObjectValue(key="message_animated_emoji_max", value=JsonNumber(value=100.0)),
    JsonObjectValue(key="new_noncontact_peers_require_premium_without_ownpremium", value=JsonBool(value=False)),
    JsonObjectValue(key="pending_suggestions", value=JsonArray(value=[
        JsonString(value="VALIDATE_PASSWORD"),
        JsonString(value="VALIDATE_PHONE_NUMBER"),
        JsonString(value="NEWCOMER_TICKS"),
        JsonString(value="SETUP_PASSWORD"),
    ])),
    JsonObjectValue(key="pm_read_date_expire_period", value=JsonNumber(value=7 * 24 * 60 * 60.0)),
    JsonObjectValue(key="premium_bot_username", value=JsonString(value="PremiumBot")),
    JsonObjectValue(key="premium_gift_attach_menu_icon", value=JsonBool(value=True)),
    JsonObjectValue(key="premium_gift_text_field_icon", value=JsonBool(value=False)),
    JsonObjectValue(key="premium_invoice_slug", value=JsonString(value="abc")),
    JsonObjectValue(key="premium_manage_subscription_url", value=JsonString(value="https://t.me/premiumbot?start=status")),
    JsonObjectValue(key="premium_promo_order", value=JsonArray(value=[
        JsonString(value="stories"),
        JsonString(value="more_upload"),
        JsonString(value="double_limits"),
        JsonString(value="business"),
        JsonString(value="last_seen"),
        JsonString(value="voice_to_text"),
        JsonString(value="faster_download"),
        JsonString(value="translations"),
        JsonString(value="animated_emoji"),
        JsonString(value="emoji_status"),
        JsonString(value="saved_tags"),
        JsonString(value="peer_colors"),
        JsonString(value="wallpapers"),
        JsonString(value="profile_badge"),
        JsonString(value="message_privacy"),
        JsonString(value="advanced_chat_management"),
        JsonString(value="no_ads"),
        JsonString(value="app_icons"),
        JsonString(value="infinite_reactions"),
        JsonString(value="animated_userpics"),
        JsonString(value="premium_stickers"),
        JsonString(value="effects"),
    ])),
    JsonObjectValue(key="premium_purchase_blocked", value=JsonBool(value=True)),
    JsonObjectValue(key="qr_login_camera", value=JsonBool(value=True)),
    JsonObjectValue(key="qr_login_code", value=JsonString(value="primary")),
    JsonObjectValue(key="quick_replies_limit", value=JsonNumber(value=100.0)),
    JsonObjectValue(key="quick_reply_messages_limit", value=JsonNumber(value=20.0)),
    JsonObjectValue(key="quote_length_max", value=JsonNumber(value=1024.0)),
    JsonObjectValue(key="reactions_in_chat_max", value=JsonNumber(value=100.0)),
    JsonObjectValue(key="reactions_uniq_max", value=JsonNumber(value=11.0)),
    JsonObjectValue(key="reactions_user_max_default", value=JsonNumber(value=1.0)),
    JsonObjectValue(key="reactions_user_max_premium", value=JsonNumber(value=3.0)),
    JsonObjectValue(key="recommended_channels_limit_default", value=JsonNumber(value=0.0)),
    JsonObjectValue(key="recommended_channels_limit_premium", value=JsonNumber(value=0.0)),
    JsonObjectValue(key="restriction_add_platforms", value=JsonArray(value=[])),
    JsonObjectValue(key="ringtone_duration_max", value=JsonNumber(value=5.0)),
    JsonObjectValue(key="ringtone_saved_count_max", value=JsonNumber(value=100.0)),
    JsonObjectValue(key="ringtone_size_max", value=JsonNumber(value=307200.0)),
    JsonObjectValue(key="round_video_encoding", value=JsonObject(value=[
        JsonObjectValue(key="diameter", value=JsonNumber(value=384.0)),
        JsonObjectValue(key="video_bitrate", value=JsonNumber(value=1000.0)),
        JsonObjectValue(key="audio_bitrate", value=JsonNumber(value=64.0)),
        JsonObjectValue(key="max_size", value=JsonNumber(value=12582912.0)),
    ])),
    JsonObjectValue(key="saved_dialogs_pinned_limit_default", value=JsonNumber(value=5.0)),
    JsonObjectValue(key="saved_dialogs_pinned_limit_premium", value=JsonNumber(value=100.0)),
    JsonObjectValue(key="saved_gifs_limit_default", value=JsonNumber(value=200.0)),
    JsonObjectValue(key="saved_gifs_limit_premium", value=JsonNumber(value=400.0)),
    JsonObjectValue(key="small_queue_max_active_operations_count", value=JsonNumber(value=5.0)),
    JsonObjectValue(key="sponsored_links_inapp_allow", value=JsonBool(value=False)),
    JsonObjectValue(key="stargifts_blocked", value=JsonBool(value=True)),
    JsonObjectValue(key="stargifts_convert_period_max", value=JsonNumber(value=7776000.0)),
    JsonObjectValue(key="stargifts_message_length_max", value=JsonNumber(value=255.0)),
    JsonObjectValue(key="starref_connect_allowed", value=JsonBool(value=False)),
    JsonObjectValue(key="starref_max_commission_permille", value=JsonNumber(value=800.0)),
    JsonObjectValue(key="starref_min_commission_permille", value=JsonNumber(value=1.0)),
    JsonObjectValue(key="starref_program_allowed", value=JsonBool(value=False)),
    JsonObjectValue(key="starref_start_param_prefixes", value=JsonArray(value=[JsonString(value="_tgr_")])),
    JsonObjectValue(key="stars_gifts_enabled", value=JsonBool(value=False)),
    JsonObjectValue(key="stars_paid_post_amount_max", value=JsonNumber(value=2500.0)),
    JsonObjectValue(key="stars_paid_reaction_amount_max", value=JsonNumber(value=2500.0)),
    JsonObjectValue(key="stars_purchase_blocked", value=JsonBool(value=True)),
    JsonObjectValue(key="stars_revenue_withdrawal_min", value=JsonNumber(value=1000.0)),
    JsonObjectValue(key="stars_subscription_amount_max", value=JsonNumber(value=2500.0)),
    JsonObjectValue(key="stars_usd_sell_rate_x1000", value=JsonNumber(value=1410.0)),
    JsonObjectValue(key="stars_usd_withdraw_rate_x1000", value=JsonNumber(value=1300.0)),
    JsonObjectValue(key="stickers_emoji_cache_time", value=JsonNumber(value=86400.0)),
    JsonObjectValue(key="stickers_emoji_suggest_only_api", value=JsonBool(value=False)),
    JsonObjectValue(key="stickers_faved_limit_default", value=JsonNumber(value=float(AppConfig.FAVED_STICKERS_LIMIT))),
    JsonObjectValue(key="stickers_faved_limit_premium", value=JsonNumber(value=float(AppConfig.FAVED_STICKERS_LIMIT))),
    JsonObjectValue(key="stickers_normal_by_emoji_per_premium_num", value=JsonNumber(value=3.0)),
    JsonObjectValue(key="stickers_premium_by_emoji_num", value=JsonNumber(value=0.0)),
    JsonObjectValue(key="stories_area_url_max", value=JsonNumber(value=3.0)),
    JsonObjectValue(key="stories_changelog_user_id", value=JsonNumber(value=777000.0)),
    JsonObjectValue(key="stories_entities", value=JsonString(value="disabled")),
    JsonObjectValue(key="stories_pinned_to_top_count_max", value=JsonNumber(value=3.0)),
    JsonObjectValue(key="stories_posting", value=JsonString(value="disabled")),
    JsonObjectValue(key="stories_sent_monthly_limit_default", value=JsonNumber(value=30.0)),
    JsonObjectValue(key="stories_sent_monthly_limit_premium", value=JsonNumber(value=3000.0)),
    JsonObjectValue(key="stories_sent_weekly_limit_default", value=JsonNumber(value=7.0)),
    JsonObjectValue(key="stories_sent_weekly_limit_premium", value=JsonNumber(value=700.0)),
    JsonObjectValue(key="stories_stealth_cooldown_period", value=JsonNumber(value=10800.0)),
    JsonObjectValue(key="stories_stealth_future_period", value=JsonNumber(value=1500.0)),
    JsonObjectValue(key="stories_stealth_past_period", value=JsonNumber(value=300.0)),
    JsonObjectValue(key="stories_suggested_reactions_limit_default", value=JsonNumber(value=1.0)),
    JsonObjectValue(key="stories_suggested_reactions_limit_premium", value=JsonNumber(value=5.0)),
    JsonObjectValue(key="stories_venue_search_username", value=JsonString(value="foursquare")),
    JsonObjectValue(key="story_caption_length_limit_default", value=JsonNumber(value=200.0)),
    JsonObjectValue(key="story_caption_length_limit_premium", value=JsonNumber(value=2048.0)),
    JsonObjectValue(key="story_expiring_limit_default", value=JsonNumber(value=3.0)),
    JsonObjectValue(key="story_expiring_limit_premium", value=JsonNumber(value=100.0)),
    JsonObjectValue(key="story_viewers_expire_period", value=JsonNumber(value=86400.0)),
    JsonObjectValue(key="story_weather_preload", value=JsonBool(value=False)),
    JsonObjectValue(key="telegram_antispam_group_size_min", value=JsonNumber(value=200.0)),
    JsonObjectValue(key="telegram_antispam_user_id", value=JsonString(value="5434988373")),
    JsonObjectValue(key="ton_proxy_address", value=JsonString(value="magic.org")),
    JsonObjectValue(key="topics_pinned_limit", value=JsonNumber(value=5.0)),
    JsonObjectValue(key="transcribe_audio_trial_duration_max", value=JsonNumber(value=300.0)),
    JsonObjectValue(key="transcribe_audio_trial_weekly_number", value=JsonNumber(value=0.0)),
    JsonObjectValue(key="upload_max_fileparts_default", value=JsonNumber(value=4000.0)),
    JsonObjectValue(key="upload_max_fileparts_premium", value=JsonNumber(value=8000.0)),
    JsonObjectValue(key="upload_premium_speedup_download", value=JsonNumber(value=10.0)),
    JsonObjectValue(key="upload_premium_speedup_notify_period", value=JsonNumber(value=3600.0)),
    JsonObjectValue(key="upload_premium_speedup_upload", value=JsonNumber(value=10.0)),
    JsonObjectValue(key="url_auth_domains", value=JsonArray(value=[])),
    JsonObjectValue(key="video_ignore_alt_documents", value=JsonBool(value=False)),
    JsonObjectValue(key="weather_search_username", value=JsonString(value="StoryWeatherBot")),
    JsonObjectValue(key="web_app_allowed_protocols", value=JsonArray(value=[
        JsonString(value="http"),
        JsonString(value="https"),
    ])),
    JsonObjectValue(key="whitelisted_domains", value=JsonArray(value=[])),
])


@handler.on_request(GetAppConfig, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_app_config(request: GetAppConfig):  # pragma: no cover
    if request.hash == APP_CONFIG_HASH:
        return AppConfigNotModified()
    return TLAppConfig(hash=APP_CONFIG_HASH, config=APP_CONFIG)


@handler.on_request(GetCountriesList, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_countries_list(request: GetCountriesList) -> CountriesList | CountriesListNotModified:
    global CACHED_COUNTRIES_LIST
    countries, cache_time = CACHED_COUNTRIES_LIST

    if time() - cache_time > 60 * 60 * 12:
        countries = CountriesList(countries=[], hash=0)

        country: AuthCountry
        for country in await AuthCountry.filter().order_by("id"):
            countries.countries.append(await country.to_tl())

            countries.hash ^= countries.hash >> 21
            countries.hash ^= countries.hash << 35
            countries.hash ^= countries.hash >> 4
            countries.hash += await country.get_internal_hash()

        countries.hash = ctypes.c_int32(countries.hash & ((2 << 32 - 1) - 1)).value
        CACHED_COUNTRIES_LIST = countries, time()

    if request.hash == countries.hash and countries.hash != 0:
        return CountriesListNotModified()

    return countries


@handler.on_request(GetTermsOfServiceUpdate, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_terms_of_service_update():  # pragma: no cover
    return TermsOfServiceUpdateEmpty(expires=int(time() + 9000))


@handler.on_request(GetPromoData, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_promo_data():  # pragma: no cover
    return PromoDataEmpty(expires=int(time() + 9000))


@handler.on_request(GetPremiumPromo, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_premium_promo():  # pragma: no cover
    return PremiumPromo(
        status_text="Premium Lol",
        status_entities=[],
        video_sections=[],
        videos=[],
        period_options=[
            PremiumSubscriptionOption(
                months=7,
                currency="EUR",
                amount=169,
                bot_url="t.me/spambot",
            ),
        ],
        users=[],
    )


@handler.on_request(SaveAppLog, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def save_app_log():  # pragma: no cover
    return True


@handler.on_request(GetInviteText, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_invite_text():  # pragma: no cover
    return InviteText(message="🐳")


@handler.on_request(GetPeerColors, ReqHandlerFlags.AUTH_NOT_REQUIRED)
@handler.on_request(GetPeerProfileColors, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_peer_colors():  # pragma: no cover
    return PeerColors(
        hash=1,
        colors=[
            PeerColorOption(color_id=color_id)
            for color_id in range(6)
        ],
    )


@handler.on_request(DismissSuggestion)
async def dismiss_suggestion() -> bool:  # pragma: no cover
    return True

