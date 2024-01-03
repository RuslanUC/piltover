from time import time

from piltover.server import MessageHandler, Client
from piltover.tl.types import CoreMessage
from piltover.tl_new import Config, DcOption, NearestDc, JsonObject, PremiumSubscriptionOption, DataJSON
from piltover.tl_new.functions.help import GetConfig, GetAppConfig, GetNearestDc, GetCountriesList, \
    GetTermsOfServiceUpdate, GetPromoData, GetPremiumPromo, SaveAppLog, GetInviteText
from piltover.tl_new.types.help import CountriesList, Country, CountryCode, TermsOfServiceUpdate, PromoDataEmpty, \
    PremiumPromo, InviteText, TermsOfService, TermsOfServiceUpdateEmpty

handler = MessageHandler("help")


# noinspection PyUnusedLocal
@handler.on_message(GetConfig)
async def get_config(client: Client, request: CoreMessage[GetConfig], session_id: int):
    return Config(
        date=int(time()),
        expires=int(time() + 60 * 10),
        this_dc=2,
        test_mode=False,
        dc_options=[DcOption(flags=0, this_port_only=True, id=2, ip_address="127.0.0.1", port=4430)],
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
        # saved_gifs_limit=100,
        edit_time_limit=48 * 60 * 60,
        revoke_time_limit=int(2 ** 31 - 1),
        revoke_pm_time_limit=int(2 ** 31 - 1),
        rating_e_decay=2,
        stickers_recent_limit=15,
        # stickers_faved_limit=5,
        channels_read_media_period=24 * 60 * 60,
        # pinned_dialogs_count_max=5,
        # pinned_infolder_count_max=200,
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
@handler.on_message(GetNearestDc)
async def get_nearest_dc(client: Client, request: CoreMessage[GetNearestDc], session_id: int):
    return NearestDc(
        country="US",  # "Y-Land",
        this_dc=2,
        nearest_dc=2,
    )


# noinspection PyUnusedLocal
@handler.on_message(GetAppConfig)
async def get_app_config(client: Client, request: CoreMessage[GetAppConfig], session_id: int):
    return JsonObject(value=[])


# noinspection PyUnusedLocal
@handler.on_message(GetCountriesList)
async def get_countries_list(client: Client, request: CoreMessage[GetCountriesList], session_id: int):
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
@handler.on_message(GetTermsOfServiceUpdate)
async def get_terms_of_service_update(client: Client, request: CoreMessage[GetTermsOfServiceUpdate], session_id: int):
    return TermsOfServiceUpdateEmpty(expires=int(time() + 9000))


# noinspection PyUnusedLocal
@handler.on_message(GetPromoData)
async def get_promo_data(client: Client, request: CoreMessage[GetPromoData], session_id: int):
    return PromoDataEmpty(expires=int(time() + 9000))


# noinspection PyUnusedLocal
@handler.on_message(GetPremiumPromo)
async def get_premium_promo(client: Client, request: CoreMessage[GetPremiumPromo], session_id: int):
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
@handler.on_message(SaveAppLog)
async def save_app_log(client: Client, request: CoreMessage[SaveAppLog], session_id: int):
    return True


# noinspection PyUnusedLocal
@handler.on_message(GetInviteText)
async def get_invite_text(client: Client, request: CoreMessage[GetInviteText], session_id: int):
    return InviteText(message="🐳")
