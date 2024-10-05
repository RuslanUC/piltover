from time import time

from piltover.high_level import MessageHandler, Client
from piltover.tl import Config, DcOption, NearestDc, JsonObject, PremiumSubscriptionOption
from piltover.tl.functions.help import GetConfig, GetAppConfig, GetNearestDc, GetCountriesList, \
    GetTermsOfServiceUpdate, GetPromoData, GetPremiumPromo, SaveAppLog, GetInviteText
from piltover.tl.types.help import CountriesList, Country, CountryCode, PromoDataEmpty, \
    PremiumPromo, InviteText, TermsOfServiceUpdateEmpty

handler = MessageHandler("help")


# noinspection PyUnusedLocal
@handler.on_request(GetConfig)
async def get_config(client: Client, request: GetConfig):
    return Config(
        date=int(time()),
        expires=int(time() + 60 * 10),
        this_dc=2,
        test_mode=False,
        dc_options=[DcOption(this_port_only=True, id=2, ip_address="127.0.0.1", port=4430)],
        dc_txt_domain_name="aa",
        chat_size_max=200,
        megagroup_size_max=200000,
        forwarded_count_max=100,
        online_update_period_ms=30_000,
        offline_blur_timeout_ms=30_000,
        offline_idle_timeout_ms=30_000,
        online_cloud_timeout_ms=30_000,
        notify_cloud_delay_ms=60_000,
        notify_default_delay_ms=10_000,
        push_chat_period_ms=1_000,
        push_chat_limit=1,
        edit_time_limit=48 * 60 * 60,
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
        caption_length_max=2048,
        message_length_max=4096,
        webfile_dc_id=2,
    )


# noinspection PyUnusedLocal
@handler.on_request(GetNearestDc)
async def get_nearest_dc(client: Client, request: GetNearestDc):
    return NearestDc(
        country="US",  # "Y-Land",
        this_dc=2,
        nearest_dc=2,
    )


# noinspection PyUnusedLocal
@handler.on_request(GetAppConfig)
async def get_app_config(client: Client, request: GetAppConfig):
    return JsonObject(value=[])


# noinspection PyUnusedLocal
@handler.on_request(GetCountriesList)
async def get_countries_list(client: Client, request: GetCountriesList):
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


# noinspection PyUnusedLocal
@handler.on_request(GetTermsOfServiceUpdate)
async def get_terms_of_service_update(client: Client, request: GetTermsOfServiceUpdate):
    return TermsOfServiceUpdateEmpty(expires=int(time() + 9000))


# noinspection PyUnusedLocal
@handler.on_request(GetPromoData)
async def get_promo_data(client: Client, request: GetPromoData):
    return PromoDataEmpty(expires=int(time() + 9000))


# noinspection PyUnusedLocal
@handler.on_request(GetPremiumPromo)
async def get_premium_promo(client: Client, request: GetPremiumPromo):
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


# noinspection PyUnusedLocal
@handler.on_request(SaveAppLog)
async def save_app_log(client: Client, request: SaveAppLog):
    return True


# noinspection PyUnusedLocal
@handler.on_request(GetInviteText)
async def get_invite_text(client: Client, request: GetInviteText):
    return InviteText(message="🐳")
