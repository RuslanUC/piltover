from time import time

from piltover.enums import ReqHandlerFlags
from piltover.high_level import MessageHandler
from piltover.tl import Config, DcOption, NearestDc, JsonObject, PremiumSubscriptionOption
from piltover.tl.functions.help import GetConfig, GetAppConfig, GetNearestDc, GetCountriesList, \
    GetTermsOfServiceUpdate, GetPromoData, GetPremiumPromo, SaveAppLog, GetInviteText, GetPeerColors, \
    GetPeerProfileColors
from piltover.tl.types.help import CountriesList, Country, CountryCode, PromoDataEmpty, \
    PremiumPromo, InviteText, TermsOfServiceUpdateEmpty, PeerColors, PeerColorOption

handler = MessageHandler("help")


@handler.on_request(GetConfig, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_config():
    return Config(
        date=int(time()),
        # This seems to be hardcoded to 1 hour on some clients, and changing it breaks them
        expires=int(time() + 60 * 60),
        this_dc=2,
        test_mode=False,
        dc_options=[
            DcOption(this_port_only=True, id=dc_id, ip_address="192.168.0.111", port=4430)
            for dc_id in range(5)
        ],
        dc_txt_domain_name="_",
        chat_size_max=10,  # Telegram default is 200
        megagroup_size_max=200000,  # Telegram default is 200000
        forwarded_count_max=100,  # Telegram default is 100
        online_update_period_ms=30_000,  # Telegram default is 210000
        offline_blur_timeout_ms=30_000,  # Telegram default is 5000
        offline_idle_timeout_ms=30_000,  # Telegram default is 30000
        online_cloud_timeout_ms=30_000,  # Telegram default is 300000
        notify_cloud_delay_ms=60_000,  # Telegram default is 30000
        notify_default_delay_ms=10_000,  # Telegram default is 1500
        push_chat_period_ms=1_000,  # Telegram default is 60000
        push_chat_limit=1,
        edit_time_limit=48 * 60 * 60,  # Telegram default is 172800
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
        caption_length_max=2048,  # Telegram default is 1024
        message_length_max=4096,
        webfile_dc_id=2,
    )


@handler.on_request(GetNearestDc, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_nearest_dc():
    return NearestDc(
        country="US",
        this_dc=2,
        nearest_dc=2,
    )


@handler.on_request(GetAppConfig, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_app_config():
    return JsonObject(value=[])


@handler.on_request(GetCountriesList, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_countries_list():
    return CountriesList(
        countries=[
            Country(
                hidden=False,
                iso2="ch",
                default_name="ch",
                name="Switzerland",
                country_codes=[
                    CountryCode(country_code="41", prefixes=["41"], patterns=["XXXXX"])
                ]
            ),
        ],
        hash=0,
    )


@handler.on_request(GetTermsOfServiceUpdate, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_terms_of_service_update():
    return TermsOfServiceUpdateEmpty(expires=int(time() + 9000))


@handler.on_request(GetPromoData, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_promo_data():
    return PromoDataEmpty(expires=int(time() + 9000))


@handler.on_request(GetPremiumPromo, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_premium_promo():
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
async def save_app_log():
    return True


@handler.on_request(GetInviteText, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_invite_text():
    return InviteText(message="🐳")


@handler.on_request(GetPeerColors, ReqHandlerFlags.AUTH_NOT_REQUIRED)
@handler.on_request(GetPeerProfileColors, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_peer_colors():
    return PeerColors(
        hash=1,
        colors=[
            PeerColorOption(color_id=color_id)
            for color_id in range(6)
        ],
    )

