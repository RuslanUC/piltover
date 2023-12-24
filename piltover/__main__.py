import asyncio
import time
from os import getenv
from pathlib import Path

import uvloop
from loguru import logger

from piltover.server import Client, CoreMessage, Server
from piltover.tl_new import InitConnection, Ping, PingDelayDisconnect, InvokeWithLayer, InvokeAfterMsg, \
    InvokeWithoutUpdates, UserStatusOnline, PeerUser, InputUserSelf, TLObject, UserEmpty, NearestDc, JsonObject, \
    SetClientDHParams, UpdateShortSentMessage, DestroySession, DestroySessionOk, RpcDropAnswer, RpcAnswerUnknown, \
    WebPageEmpty, RpcError, SecurePasswordKdfAlgoSHA512, \
    PasswordKdfAlgoSHA256SHA256PBKDF2HMACSHA512iter100000SHA256ModPow
from piltover.tl_new.functions.account import GetDefaultEmojiStatuses, UpdateStatus, UpdateProfile, GetNotifySettings, \
    GetThemes, GetGlobalPrivacySettings, GetContentSettings, GetPassword, GetContactSignUpNotification, GetPrivacy, \
    GetAuthorizations, GetAccountTTL, RegisterDevice, UpdateUsername, CheckUsername
from piltover.tl_new.functions.auth import SendCode, SignIn, BindTempAuthKey, ExportLoginToken
from piltover.tl_new.functions.contacts import GetContacts, ResolveUsername, GetBlocked, Search, GetStatuses, \
    GetTopPeers
from piltover.tl_new.functions.help import GetConfig, GetNearestDc, GetAppConfig, GetCountriesList, GetPromoData, \
    GetTermsOfServiceUpdate, GetPremiumPromo, GetInviteText, SaveAppLog
from piltover.tl_new.functions.langpack import GetLanguages, GetStrings, GetLangPack
from piltover.tl_new.functions.messages import GetAvailableReactions, GetDialogFilters, GetPeerDialogs, \
    GetEmojiKeywordsLanguages, GetScheduledHistory, GetPeerSettings, SetTyping, GetHistory, SendMessage, ReadHistory, \
    GetWebPage, GetStickerSet, GetTopReactions, GetRecentReactions, GetAttachMenuBots, GetDialogs, GetStickers, \
    ReorderPinnedDialogs, GetPinnedDialogs, GetDefaultHistoryTTL, GetSearchResultsPositions, GetSearchCounters, \
    Search as MsgSearch, SearchGlobal, GetFavedStickers, GetAllDrafts, GetFeaturedEmojiStickers, GetFeaturedStickers, \
    GetSuggestedDialogFilters
from piltover.tl_new.functions.photos import GetUserPhotos
from piltover.tl_new.functions.stories import GetAllStories
from piltover.tl_new.functions.updates import GetState
from piltover.tl_new.functions.users import GetFullUser, GetUsers
from piltover.tl_new.types import MsgsAck, Pong, Config, DcOption, User, UserFull as FullUser, PeerSettings, \
    PeerNotifySettings, StoriesStealthMode, NearestDc, LangPackLanguage, Dialog, Message, StickerSet, AttachMenuBots, \
    GlobalPrivacySettings, PremiumSubscriptionOption, DefaultHistoryTTL, AccountDaysTTL, Authorization, Updates, \
    LangPackDifference, LangPackString
from piltover.tl_new.types.account import EmojiStatuses, PrivacyRules, Password, ContentSettings, Themes, Authorizations
from piltover.tl_new.types.auth import SentCode, SentCodeTypeSms, Authorization, LoginToken
from piltover.tl_new.types.contacts import Contacts, Found, Blocked, TopPeers
from piltover.tl_new.types.help import CountriesList, Country, CountryCode, TermsOfServiceUpdate, PromoDataEmpty, \
    PremiumPromo, InviteText
from piltover.tl_new.types.messages import AvailableReactions, Messages, PeerDialogs, AffectedMessages, \
    StickerSet as MsgStickerSet, Reactions, Dialogs, Stickers, SearchCounter, SearchResultsPositions, FeaturedStickers, \
    FavedStickers
from piltover.tl_new.types.photos import Photos
from piltover.tl_new.types.stories import AllStories
from piltover.tl_new.types.updates import State
from piltover.tl_new.types.users import UserFull
from piltover.types import Keys
from piltover.utils import gen_keys, get_public_key_fingerprint

root = Path(__file__).parent.parent.resolve(strict=True)
data = root / "data"
data.mkdir(parents=True, exist_ok=True)

secrets = data / "secrets"
secrets.mkdir(parents=True, exist_ok=True)

privkey = secrets / "privkey.asc"
pubkey = secrets / "pubkey.asc"

if not getenv("DISABLE_HR"):
    # Hot code reloading
    import jurigged


    def log(s: jurigged.live.WatchOperation):
        if hasattr(s, "filename") and "unknown" not in s.filename:
            file = Path(s.filename)
            print("Reloaded", file.relative_to(root))


    jurigged.watch("piltover/*.py", logger=log)


async def main():
    if not (pubkey.exists() and privkey.exists()):
        with privkey.open("w+") as priv, pubkey.open("w+") as pub:
            keys: Keys = gen_keys()
            priv.write(keys.private_key)
            pub.write(keys.public_key)

    private_key = privkey.read_text()
    public_key = pubkey.read_text()

    fp = get_public_key_fingerprint(public_key, signed=True)
    logger.info(
        "Pubkey fingerprint: {fp:x} ({no_sign})",
        fp=fp,
        no_sign=fp.to_bytes(8, "big", signed=True).hex(),
    )

    pilt = Server(
        server_keys=Keys(
            private_key=private_key,
            public_key=public_key,
        )
    )

    # noinspection PyUnusedLocal
    @pilt.on_message(MsgsAck)
    async def msgs_ack(client: Client, request: CoreMessage[MsgsAck], session_id: int):
        print(request.obj, request.message_id)
        return False

    # noinspection PyUnusedLocal
    @pilt.on_message(Ping)
    async def pong(client: Client, request: CoreMessage[Ping], session_id: int):
        print(request.obj, request.message_id)

        logger.success("Sent ping ping_id={ping_id}", ping_id=request.obj.ping_id)

        return Pong(msg_id=request.message_id, ping_id=request.obj.ping_id)

    # noinspection PyUnusedLocal
    @pilt.on_message(PingDelayDisconnect)
    async def ping_delay_disconnect(client: Client, request: CoreMessage[PingDelayDisconnect], session_id: int):
        # TODO: disconnect
        return Pong(msg_id=request.message_id, ping_id=request.obj.ping_id)

    @pilt.on_message(InvokeWithLayer)
    async def invoke_with_layer(client: Client, request: CoreMessage[InvokeWithLayer], session_id: int):
        return await client.propagate(
            CoreMessage(
                obj=request.obj.query,
                message_id=request.message_id,
                seq_no=request.seq_no,
            ),
            session_id,
            just_return=True,
        )

    @pilt.on_message(InvokeAfterMsg)
    async def invoke_after_msg(client: Client, request: CoreMessage[InvokeAfterMsg], session_id: int):
        return await client.propagate(
            CoreMessage(
                obj=request.obj.query,
                message_id=request.message_id,
                seq_no=request.seq_no,
            ),
            session_id,
            just_return=True,
        )

    @pilt.on_message(InvokeWithoutUpdates)
    async def invoke_without_updates(client: Client, request: CoreMessage[InvokeWithoutUpdates], session_id: int):
        return await client.propagate(
            CoreMessage(
                obj=request.obj.query,
                message_id=request.message_id,
                seq_no=request.seq_no,
            ),
            session_id,
            just_return=True,
        )

    @pilt.on_message(InitConnection)
    async def init_connection(client: Client, request: CoreMessage, session_id: int):
        # hmm yes yes, I trust you client
        # the api id is always correct, it has always been!

        print("initConnection with Api ID:", request.obj.api_id)

        return await client.propagate(
            CoreMessage(
                obj=request.obj.query,
                message_id=request.message_id,
                seq_no=request.seq_no,
            ),
            session_id,
            just_return=True,
        )

    # noinspection PyUnusedLocal
    @pilt.on_message(GetConfig)
    async def get_config(client: Client, request: CoreMessage[GetConfig], session_id: int):
        return Config(
            date=int(time.time()),
            expires=int(time.time() + 60 * 10),
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
            saved_gifs_limit=100,
            edit_time_limit=48 * 60 * 60,
            revoke_time_limit=int(2 ** 31 - 1),
            revoke_pm_time_limit=int(2 ** 31 - 1),
            rating_e_decay=2,
            stickers_recent_limit=15,
            stickers_faved_limit=5,
            channels_read_media_period=24 * 60 * 60,
            pinned_dialogs_count_max=5,
            pinned_infolder_count_max=200,
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
    @pilt.on_message(SendCode)
    async def send_code(client: Client, request: CoreMessage[SendCode], session_id: int):
        from binascii import crc32

        code = 69696
        code = str(code).encode()

        return SentCode(
            type=SentCodeTypeSms(length=len(code)),
            phone_code_hash=f"{crc32(code):x}".zfill(8),
            timeout=30,
        )

    user = User(
        is_self=True,
        contact=False,
        mutual_contact=False,
        deleted=False,
        bot=False,
        verified=True,
        restricted=False,
        min=False,
        support=False,
        scam=False,
        apply_min_photo=False,
        fake=False,
        bot_attach_menu=False,
        premium=False,
        attach_menu_enabled=False,
        id=123456,
        access_hash=0,
        first_name="Testing",
        last_name=":)",
        username="test",
        phone="123456",
        lang_code="en",
    )

    durov = User(
        is_self=True,
        contact=False,
        mutual_contact=False,
        deleted=False,
        bot=False,
        verified=True,
        restricted=False,
        min=False,
        support=False,
        scam=False,
        apply_min_photo=False,
        fake=False,
        bot_attach_menu=False,
        premium=False,
        attach_menu_enabled=False,
        id=42123,
        access_hash=0,
        first_name="Pavel",
        last_name="Durov",
        username="durov7",
        phone="+4442123",
        status=UserStatusOnline(expires=int(time.time() + 9000)),
        lang_code="en",
    )

    durov_message = {
        "_": "message",
        "id": 456,
        "peer_id": PeerUser(user_id=durov.id),
        "date": int(time.time() - 150),
        "message": "Приветик",
    }

    # noinspection PyUnusedLocal
    @pilt.on_message(SignIn)
    async def sign_in(client: Client, request: CoreMessage[SignIn], session_id: int):
        return Authorization(flags=0, user=user)

    # noinspection PyUnusedLocal
    @pilt.on_message(GetState)
    async def get_state(client: Client, request: CoreMessage[GetState], session_id: int):
        return State(
            pts=0,
            qts=0,
            seq=0,
            date=int(time.time()),
            unread_count=0,
        )

    # noinspection PyUnusedLocal
    @pilt.on_message(GetFullUser)
    async def get_full_user(client: Client, request: CoreMessage, session_id: int):
        if isinstance(request.obj, InputUserSelf):
            return UserFull(
                full_user=FullUser(
                    flags=0,
                    blocked=False,
                    phone_calls_available=False,
                    phone_calls_private=False,
                    can_pin_message=True,
                    has_scheduled=False,
                    video_calls_available=False,
                    voice_messages_forbidden=True,
                    id=user.id,
                    about="hi, this is a test bio",
                    settings=PeerSettings(),
                    profile_photo=None,
                    notify_settings=PeerNotifySettings(
                        show_previews=True,
                        silent=False,
                    ),
                    common_chats_count=0,
                ),
                chats=[],
                users=[user],
            )
        logger.warning("id: inputUser is not inputUserSelf: not implemented")

    # noinspection PyUnusedLocal
    @pilt.on_message(GetUsers)
    async def get_users(client: Client, request: CoreMessage[GetUsers], session_id: int):
        result: list[TLObject] = []

        for peer in request.obj.id:
            if isinstance(peer, InputUserSelf):
                result.append(user)
            else:
                # TODO: other input users
                result.append(UserEmpty(id=0))

        return result

    # noinspection PyUnusedLocal
    @pilt.on_message(GetAllStories)
    async def get_all_stories(client: Client, request: CoreMessage[GetAllStories], session_id: int):
        return AllStories(
            has_more=False,
            count=0,
            state="",
            peer_stories=[],
            chats=[],
            users=[],
            stealth_mode=StoriesStealthMode(
                active_until_date=0,
                cooldown_until_date=0,
            ),
        )

    # noinspection PyUnusedLocal
    @pilt.on_message(BindTempAuthKey)
    async def bind_temp_auth_key(client: Client, request: CoreMessage[BindTempAuthKey], session_id: int):
        return True

    # noinspection PyUnusedLocal
    @pilt.on_message(GetNearestDc)
    async def get_nearest_dc(client: Client, request: CoreMessage[GetNearestDc], session_id: int):
        return NearestDc(
            country="US",  # "Y-Land",
            this_dc=2,
            nearest_dc=2,
        )

    # noinspection PyUnusedLocal
    @pilt.on_message(GetAppConfig)
    async def get_app_config(client: Client, request: CoreMessage[GetAppConfig], session_id: int):
        return JsonObject(value=[])

    # noinspection PyUnusedLocal
    @pilt.on_message(GetLanguages)
    async def get_languages(client: Client, request: CoreMessage[GetLanguages], session_id: int):
        return [LangPackLanguage(name="Gramz", native_name="Le Gramz", lang_code="grz")]

    # noinspection PyUnusedLocal
    @pilt.on_message(GetCountriesList)
    async def get_countries_list(client: Client, request: CoreMessage[GetCountriesList], session_id: int):
        CountriesList(
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
    @pilt.on_message(ExportLoginToken)
    async def export_login_token(client: Client, request: CoreMessage[ExportLoginToken], session_id: int):
        return LoginToken(expires=1000, token=b"levlam")

    """
    @pilt.on_message("msgs_state_req")
    async def msgs_state_req(client: Client, request: CoreMessage, session_id: int):
        ...
    """

    # noinspection PyUnusedLocal
    @pilt.on_message(GetDialogFilters)
    async def get_dialog_filters(client: Client, request: CoreMessage[GetDialogFilters], session_id: int):
        return []

    # noinspection PyUnusedLocal
    @pilt.on_message(GetAvailableReactions)
    async def get_available_reactions(client: Client, request: CoreMessage[GetAvailableReactions], session_id: int):
        return AvailableReactions(hash=0, reactions=[])

    # noinspection PyUnusedLocal
    @pilt.on_message(GetDefaultEmojiStatuses)
    async def get_default_emoji_statuses(client: Client, request: CoreMessage[GetDefaultEmojiStatuses],
                                         session_id: int):
        return EmojiStatuses(hash=0, statuses=[])

    # noinspection PyUnusedLocal
    @pilt.on_message(SetClientDHParams)
    async def set_client_dh_params(client: Client, request: CoreMessage[SetClientDHParams], session_id: int):
        print(request.obj)
        # print(client.shared)
        raise

    # noinspection PyUnusedLocal
    @pilt.on_message(SetTyping)
    async def set_typing(client: Client, request: CoreMessage[SetTyping], session_id: int):
        return True

    # noinspection PyUnusedLocal
    @pilt.on_message(GetPeerSettings)
    async def get_peer_settings(client: Client, request: CoreMessage[GetPeerSettings], session_id: int):
        return PeerSettings()

    # noinspection PyUnusedLocal
    @pilt.on_message(GetScheduledHistory)
    async def get_scheduled_history(client: Client, request: CoreMessage[GetScheduledHistory], session_id: int):
        return Messages(messages=[], chats=[], users=[])

    # noinspection PyUnusedLocal
    @pilt.on_message(GetEmojiKeywordsLanguages)
    async def get_emoji_keywords_languages(client: Client, request: CoreMessage[GetEmojiKeywordsLanguages],
                                           session_id: int):
        return []

    @pilt.on_message(GetPeerDialogs)
    async def get_peer_dialogs(client: Client, request: CoreMessage[GetPeerDialogs], session_id: int):
        return PeerDialogs(
            dialogs=[
                Dialog(
                    peer=PeerUser(user_id=durov.id),
                    top_message=0,
                    read_inbox_max_id=0,
                    read_outbox_max_id=0,
                    unread_count=0,
                    unread_mentions_count=0,
                    unread_reactions_count=0,
                    notify_settings=await get_notify_settings(
                        client, request, session_id
                    ),
                )
            ],
            messages=[durov_message],
            chats=[],
            users=[durov],
            state=await get_state(client, request, session_id)
        )

    # noinspection PyUnusedLocal
    @pilt.on_message(GetHistory)
    async def get_history(client: Client, request: CoreMessage[GetHistory], session_id: int):
        if request.obj.peer.user_id == durov.id:
            return Messages(messages=[durov_message], chats=[], users=[])

        if request.obj.offset_id != 0:
            return Messages(messages=[], chats=[], users=[])

        return Messages(
            messages=[
                Message(
                    out=True,
                    mentioned=True,
                    media_unread=False,
                    silent=False,
                    post=True,
                    from_scheduled=False,
                    legacy=True,
                    edit_hide=True,
                    pinned=False,
                    noforwards=False,
                    id=1,
                    from_id=PeerUser(user_id=user.id),
                    peer_id=PeerUser(user_id=user.id),
                    date=int(time.time() - 120),
                    message="aaaaaa",
                    media=None,
                    entities=None,
                    views=40,
                    forwards=None,
                    edit_date=None,
                    post_author=None,
                    grouped_id=None,
                    reactions=None,
                    restriction_reason=None,
                    ttl_period=None,
                )
            ],
            chats=[],
            users=[]
        )

    # noinspection PyUnusedLocal
    @pilt.on_message(UpdateStatus)
    async def update_status(client: Client, request: CoreMessage[UpdateStatus], session_id: int):
        return True

    # noinspection PyUnusedLocal
    @pilt.on_message(SendMessage)
    async def send_message(client: Client, request: CoreMessage[SendMessage], session_id: int):
        return UpdateShortSentMessage(
            out=True,
            id=2,
            pts=2,
            pts_count=2,
            date=int(time.time()),
        )

    # noinspection PyUnusedLocal
    @pilt.on_message(ReadHistory)
    async def read_history(client: Client, request: CoreMessage[ReadHistory], session_id: int):
        return AffectedMessages(
            pts=3,
            pts_count=1,
        )

    # noinspection PyUnusedLocal
    @pilt.on_message(DestroySession)
    async def destroy_session(client: Client, request: CoreMessage[DestroySession], session_id: int):
        return DestroySessionOk(session_id=request.obj.session_id)

    # noinspection PyUnusedLocal
    @pilt.on_message(RpcDropAnswer)
    async def rpc_drop_answer(client: Client, request: CoreMessage[RpcDropAnswer], session_id: int):
        return RpcAnswerUnknown()

    # noinspection PyUnusedLocal
    @pilt.on_message(GetWebPage)
    async def get_web_page(client: Client, request: CoreMessage[GetWebPage], session_id: int):
        return WebPageEmpty()

    # noinspection PyUnusedLocal
    @pilt.on_message(GetUserPhotos)
    async def get_user_photos(client: Client, request: CoreMessage[GetUserPhotos], session_id: int):
        return Photos(
            photos=[],
            users=[user],
        )

    # noinspection PyUnusedLocal
    @pilt.on_message(GetStickerSet)
    async def get_sticker_set(client: Client, request: CoreMessage[GetStickerSet], session_id: int):
        import random

        return MsgStickerSet(
            set=StickerSet(
                official=True,
                id=random.randint(1000000, 9000000),
                access_hash=random.randint(1000000, 9000000),
                title="Picker Stack",
                short_name=random.randbytes(5).hex(),
                count=0,
                hash=0,
            ),
            packs=[],
            keywords=[],
            documents=[],
        )

    # noinspection PyUnusedLocal
    @pilt.on_message(UpdateProfile)
    async def update_profile(client: Client, request: CoreMessage[UpdateProfile], session_id: int):
        if request.obj.first_name is not None:
            user.first_name = request.obj.first_name
        if request.obj.last_name is not None:
            user.last_name = request.obj.last_name
        if request.obj.about is not None:
            user.about = request.obj.about
        return user

    # noinspection PyUnusedLocal
    @pilt.on_message(GetTopReactions)
    async def get_top_reactions(client: Client, request: CoreMessage[GetTopReactions], session_id: int):
        return Reactions(hash=0, reactions=[])

    # noinspection PyUnusedLocal
    @pilt.on_message(GetRecentReactions)
    async def get_recent_reactions(client: Client, request: CoreMessage[GetRecentReactions], session_id: int):
        return Reactions(hash=0, reactions=[])

    # noinspection PyUnusedLocal
    @pilt.on_message(GetDialogs)
    async def get_dialogs(client: Client, request: CoreMessage[GetDialogs], session_id: int):
        return Dialogs(
            dialogs=[],
            messages=[],
            chats=[],
            users=[],
        )

    # noinspection PyUnusedLocal
    @pilt.on_message(GetAttachMenuBots)
    async def get_attach_menu_bots(client: Client, request: CoreMessage[GetAttachMenuBots], session_id: int):
        return AttachMenuBots(
            hash=0,
            bots=[],
            users=[],
        )

    # noinspection PyUnusedLocal
    @pilt.on_message(GetNotifySettings)
    async def get_notify_settings(client: Client, request: CoreMessage[GetNotifySettings], session_id: int):
        return PeerNotifySettings(
            show_previews=True,
            silent=False,
        )

    # noinspection PyUnusedLocal
    @pilt.on_message(GetContacts)
    async def get_contacts(client: Client, request: CoreMessage[GetContacts], session_id: int):
        return Contacts(
            contacts=[],
            saved_count=0,
            users=[],
        )

    # noinspection PyUnusedLocal
    @pilt.on_message(GetTermsOfServiceUpdate)
    async def get_terms_of_service_update(client: Client, request: CoreMessage[GetTermsOfServiceUpdate],
                                          session_id: int):
        return TermsOfServiceUpdate(expires=int(time.time() + 9000))

    @pilt.on_message(GetPinnedDialogs)
    async def get_pinned_dialogs(client: Client, request: CoreMessage[GetPinnedDialogs], session_id: int):
        return PeerDialogs(
            dialogs=[],
            messages=[],
            chats=[],
            users=[],
            state=await get_state(client, request, session_id),
        )

    # noinspection PyUnusedLocal
    @pilt.on_message(ReorderPinnedDialogs)
    async def reorder_pinned_dialogs(client: Client, request: CoreMessage[ReorderPinnedDialogs], session_id: int):
        return True

    # noinspection PyUnusedLocal
    @pilt.on_message(GetPromoData)
    async def get_promo_data(client: Client, request: CoreMessage[GetPromoData], session_id: int):
        return PromoDataEmpty(expires=int(time.time() + 9000))

    # noinspection PyUnusedLocal
    @pilt.on_message(GetStickers)
    async def get_stickers(client: Client, request: CoreMessage[GetStickers], session_id: int):
        return Stickers(hash=0, stickers=[])

    # noinspection PyUnusedLocal
    @pilt.on_message(ResolveUsername)
    async def resolve_username(client: Client, request: CoreMessage[ResolveUsername], session_id: int):
        return RpcError(error_code=400, error_message="USERNAME_NOT_OCCUPIED")

    # noinspection PyUnusedLocal
    @pilt.on_message(GetPremiumPromo)
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
    @pilt.on_message(GetThemes)
    async def get_themes(client: Client, request: CoreMessage[GetThemes], session_id: int):
        return Themes(hash=0, themes=[])

    # noinspection PyUnusedLocal
    @pilt.on_message(GetGlobalPrivacySettings)
    async def get_global_privacy_settings(client: Client, request: CoreMessage[GetGlobalPrivacySettings],
                                          session_id: int):
        return GlobalPrivacySettings(archive_and_mute_new_noncontact_peers=True)

    # noinspection PyUnusedLocal
    @pilt.on_message(GetContentSettings)
    async def get_content_settings(client: Client, request: CoreMessage[GetContentSettings], session_id: int):
        return ContentSettings(
            sensitive_enabled=True,
            sensitive_can_change=True,
        )

    # noinspection PyUnusedLocal
    @pilt.on_message(GetContactSignUpNotification)
    async def get_contact_sign_up_notification(client: Client, request: CoreMessage[GetContactSignUpNotification],
                                               session_id: int):
        return True

    # noinspection PyUnusedLocal
    @pilt.on_message(GetPassword)
    async def get_password(client: Client, request: CoreMessage[GetPassword], session_id: int):
        return Password(
            has_password=False,
            new_algo=PasswordKdfAlgoSHA256SHA256PBKDF2HMACSHA512iter100000SHA256ModPow(
                salt1=b"asd",
                salt2=b"asd",
                g=2,
                p=b"a" * (2048 // 8),
            ),
            new_secure_algo=SecurePasswordKdfAlgoSHA512(
                salt=b"1234"
            ),
            secure_random=b"123456"
        )

    # noinspection PyUnusedLocal
    @pilt.on_message(GetPrivacy)
    async def get_privacy(client: Client, request: CoreMessage[GetPrivacy], session_id: int):
        return PrivacyRules(
            rules=[],
            chats=[],
            users=[],
        )

    # noinspection PyUnusedLocal
    @pilt.on_message(GetBlocked)
    async def get_blocked(client: Client, request: CoreMessage[GetBlocked], session_id: int):
        return Blocked(
            blocked=[],
            chats=[],
            users=[],
        )

    # noinspection PyUnusedLocal
    @pilt.on_message(GetAuthorizations)
    async def get_authorizations(client: Client, request: CoreMessage[GetAuthorizations], session_id: int):
        return Authorizations(
            authorization_ttl_days=15,
            authorizations=[
                Authorization(
                    current=True,
                    official_app=True,
                    encrypted_requests_disabled=True,
                    call_requests_disabled=True,
                    hash=0,
                    device_model="Blackberry",
                    platform="Desktop",
                    system_version="42.777.3",
                    api_id=12345,
                    app_name="DTeskdop",
                    app_version="1.2.3",
                    date_created=int(time.time() - 20),
                    date_active=int(time.time()),
                    ip="127.0.0.1",
                    country="US",  # "Y-Land",
                    region="Telegram HQ",
                ),
            ],
        )

    # noinspection PyUnusedLocal
    @pilt.on_message(GetAccountTTL)
    async def get_account_ttl(client: Client, request: CoreMessage[GetAccountTTL], session_id: int):
        return AccountDaysTTL(days=15)

    # noinspection PyUnusedLocal
    @pilt.on_message(GetDefaultHistoryTTL)
    async def get_default_history_ttl(client: Client, request: CoreMessage[GetDefaultHistoryTTL], session_id: int):
        return DefaultHistoryTTL(period=10)

    # noinspection PyUnusedLocal
    @pilt.on_message(RegisterDevice)
    async def register_device(client: Client, request: CoreMessage[RegisterDevice], session_id: int):
        return True

    # noinspection PyUnusedLocal
    @pilt.on_message(Search)
    async def contacts_search(client: Client, request: CoreMessage[Search], session_id: int):
        return Found(
            my_results=[],
            results=[],
            chats=[],
            users=[],
        )

    # noinspection PyUnusedLocal
    @pilt.on_message(GetSearchResultsPositions)
    async def get_search_results_positions(client: Client, request: CoreMessage[GetSearchResultsPositions],
                                           session_id: int):
        return SearchResultsPositions(
            count=0,
            positions=[],
        )

    # noinspection PyUnusedLocal
    @pilt.on_message(MsgSearch)
    async def messages_search(client: Client, request: CoreMessage[Search], session_id: int):
        return Messages(
            messages=[],
            chats=[],
            users=[],
        )

    # noinspection PyUnusedLocal
    @pilt.on_message(GetSearchCounters)
    async def get_search_counters(client: Client, request: CoreMessage[GetSearchCounters], session_id: int):
        return [
            SearchCounter(filter=flt, count=0) for flt in request.obj.filters
        ]

    # noinspection PyUnusedLocal
    @pilt.on_message(GetInviteText)
    async def get_invite_text(client: Client, request: CoreMessage[GetInviteText], session_id: int):
        return InviteText(message="🐳")

    # noinspection PyUnusedLocal
    @pilt.on_message(SaveAppLog)
    async def save_app_log(client: Client, request: CoreMessage[SaveAppLog], session_id: int):
        return True

    # noinspection PyUnusedLocal
    @pilt.on_message(GetSuggestedDialogFilters)
    async def get_suggested_dialog_filters(client: Client, request: CoreMessage[GetSuggestedDialogFilters],
                                           session_id: int):
        return []

    # noinspection PyUnusedLocal
    @pilt.on_message(GetTopPeers)
    async def get_top_peers(client: Client, request: CoreMessage[GetTopPeers], session_id: int):
        return TopPeers(
            categories=[],
            chats=[],
            users=[],
        )

    # noinspection PyUnusedLocal
    @pilt.on_message(GetFeaturedStickers)
    @pilt.on_message(GetFeaturedEmojiStickers)
    async def get_featured_stickers(client: Client,
                                    request: CoreMessage[GetFeaturedStickers | GetFeaturedEmojiStickers],
                                    session_id: int):
        return FeaturedStickers(
            hash=0,
            count=0,
            sets=[],
            unread=[],
        )

    # noinspection PyUnusedLocal
    @pilt.on_message(GetAllDrafts)
    async def get_all_drafts(client: Client, request: CoreMessage[GetAllDrafts], session_id: int):
        return Updates(
            updates=[],  # list of updateDraftMessage
            users=[],
            chats=[],
            date=int(time.time()),
            seq=0,
        )

    # noinspection PyUnusedLocal
    @pilt.on_message(GetStatuses)
    async def get_statuses(client: Client, request: CoreMessage[GetStatuses], session_id: int):
        return []

    # noinspection PyUnusedLocal
    @pilt.on_message(GetFavedStickers)
    async def get_faved_stickers(client: Client, request: CoreMessage[GetFavedStickers], session_id: int):
        return FavedStickers(
            hash=0,
            packs=[],
            stickers=[],
        )

    # noinspection PyUnusedLocal
    @pilt.on_message(SearchGlobal)
    async def search_global(client: Client, request: CoreMessage[SearchGlobal], session_id: int):
        return Messages(
            messages=[],
            chats=[],
            users=[],
        )

    # noinspection PyUnusedLocal
    @pilt.on_message(CheckUsername)
    async def check_username(client: Client, request: CoreMessage[CheckUsername], session_id: int):
        return True

    # noinspection PyUnusedLocal
    @pilt.on_message(UpdateUsername)
    async def update_username(client: Client, request: CoreMessage[UpdateUsername], session_id: int):
        user.username = request.obj.username
        return user

    # noinspection PyUnusedLocal
    @pilt.on_message(GetLangPack)
    async def get_lang_pack(client: Client, request: CoreMessage[GetLangPack], session_id: int):
        return LangPackDifference(
            lang_code="US",
            from_version=1,
            version=1,
            strings=[],
        )

    # noinspection PyUnusedLocal
    @pilt.on_message(GetStrings)
    async def get_strings(client: Client, request: CoreMessage[GetStrings], session_id: int):
        return [
            LangPackString(key=key, value=key.upper()) for key in request.obj.keys
        ]

    logger.success("Running on {host}:{port}", host=pilt.HOST, port=pilt.PORT)
    await pilt.serve()


if __name__ == "__main__":
    try:
        uvloop.install()
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
