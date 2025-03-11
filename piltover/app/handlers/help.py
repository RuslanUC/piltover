import ctypes
from time import time

from piltover.app_config import AppConfig
from piltover.db.models import AuthCountry
from piltover.enums import ReqHandlerFlags
from piltover.tl import Config, DcOption, NearestDc, JsonObject, PremiumSubscriptionOption
from piltover.tl.functions.help import GetConfig, GetAppConfig, GetNearestDc, GetCountriesList, \
    GetTermsOfServiceUpdate, GetPromoData, GetPremiumPromo, SaveAppLog, GetInviteText, GetPeerColors, \
    GetPeerProfileColors
from piltover.tl.types.help import CountriesList, PromoDataEmpty, PremiumPromo, InviteText, TermsOfServiceUpdateEmpty, \
    PeerColors, PeerColorOption, AppConfig as TLAppConfig, CountriesListNotModified
from piltover.worker import MessageHandler

handler = MessageHandler("help")
CACHED_COUNTRIES_LIST: tuple[CountriesList | None, int] = (None, 0)


@handler.on_request(GetConfig, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_config():
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
    )


@handler.on_request(GetNearestDc, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_nearest_dc():  # pragma: no cover
    return NearestDc(
        country="US",
        this_dc=AppConfig.THIS_DC_ID,
        nearest_dc=AppConfig.THIS_DC_ID,
    )


@handler.on_request(GetAppConfig, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_app_config():  # pragma: no cover
    return TLAppConfig(hash=1, config=JsonObject(value=[]))


@handler.on_request(GetCountriesList, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_countries_list(request: GetCountriesList) -> CountriesList | CountriesListNotModified:
    global CACHED_COUNTRIES_LIST
    countries, cache_time = CACHED_COUNTRIES_LIST

    if time() - cache_time > 60 * 60 * 12:
        countries = CountriesList(countries=[], hash=0)

        country: AuthCountry
        async for country in AuthCountry.filter().order_by("id"):
            countries.countries.append(await country.to_tl())

            countries.hash ^= countries.hash >> 21
            countries.hash ^= countries.hash << 35
            countries.hash ^= countries.hash >> 4
            countries.hash += await country.get_internal_hash()

        countries.hash = ctypes.c_int32(countries.hash & 0xffffffff).value
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

