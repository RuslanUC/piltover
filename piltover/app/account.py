from time import time

from piltover.app import user
from piltover.server import MessageHandler, Client
from piltover.tl.types import CoreMessage
from piltover.tl_new import PeerNotifySettings, GlobalPrivacySettings, \
    PasswordKdfAlgoSHA256SHA256PBKDF2HMACSHA512iter100000SHA256ModPow, \
    SecurePasswordKdfAlgoSHA512, AccountDaysTTL, Authorization
from piltover.tl_new.functions.account import UpdateStatus, UpdateProfile, GetNotifySettings, GetDefaultEmojiStatuses, \
    GetContentSettings, GetThemes, GetGlobalPrivacySettings, GetPrivacy, GetPassword, GetContactSignUpNotification, \
    RegisterDevice, GetAccountTTL, GetAuthorizations, UpdateUsername, CheckUsername
from piltover.tl_new.types.account import EmojiStatuses, Themes, ContentSettings, PrivacyRules, Password, Authorizations

handler = MessageHandler("account")


# noinspection PyUnusedLocal
@handler.on_message(CheckUsername)
async def check_username(client: Client, request: CoreMessage[CheckUsername], session_id: int):
    return True


# noinspection PyUnusedLocal
@handler.on_message(UpdateUsername)
async def update_username(client: Client, request: CoreMessage[UpdateUsername], session_id: int):
    user.username = request.obj.username
    return user


# noinspection PyUnusedLocal
@handler.on_message(GetAuthorizations)
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
                date_created=int(time() - 20),
                date_active=int(time()),
                ip="127.0.0.1",
                country="US",  # "Y-Land",
                region="Telegram HQ",
            ),
        ],
    )


# noinspection PyUnusedLocal
@handler.on_message(GetAccountTTL)
async def get_account_ttl(client: Client, request: CoreMessage[GetAccountTTL], session_id: int):
    return AccountDaysTTL(days=15)


# noinspection PyUnusedLocal
@handler.on_message(RegisterDevice)
async def register_device(client: Client, request: CoreMessage[RegisterDevice], session_id: int):
    return True


# noinspection PyUnusedLocal
@handler.on_message(GetContactSignUpNotification)
async def get_contact_sign_up_notification(client: Client, request: CoreMessage[GetContactSignUpNotification],
                                           session_id: int):
    return True


# noinspection PyUnusedLocal
@handler.on_message(GetPassword)
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
@handler.on_message(GetPrivacy)
async def get_privacy(client: Client, request: CoreMessage[GetPrivacy], session_id: int):
    return PrivacyRules(
        rules=[],
        chats=[],
        users=[],
    )


# noinspection PyUnusedLocal
@handler.on_message(GetThemes)
async def get_themes(client: Client, request: CoreMessage[GetThemes], session_id: int):
    return Themes(hash=0, themes=[])


# noinspection PyUnusedLocal
@handler.on_message(GetGlobalPrivacySettings)
async def get_global_privacy_settings(client: Client, request: CoreMessage[GetGlobalPrivacySettings],
                                      session_id: int):
    return GlobalPrivacySettings(archive_and_mute_new_noncontact_peers=True)


# noinspection PyUnusedLocal
@handler.on_message(GetContentSettings)
async def get_content_settings(client: Client, request: CoreMessage[GetContentSettings], session_id: int):
    return ContentSettings(
        sensitive_enabled=True,
        sensitive_can_change=True,
    )


# noinspection PyUnusedLocal
@handler.on_message(UpdateStatus)
async def update_status(client: Client, request: CoreMessage[UpdateStatus], session_id: int):
    return True


# noinspection PyUnusedLocal
@handler.on_message(UpdateProfile)
async def update_profile(client: Client, request: CoreMessage[UpdateProfile], session_id: int):
    if request.obj.first_name is not None:
        user.first_name = request.obj.first_name
    if request.obj.last_name is not None:
        user.last_name = request.obj.last_name
    if request.obj.about is not None:
        user.about = request.obj.about
    return user


# noinspection PyUnusedLocal
@handler.on_message(GetNotifySettings)
async def get_notify_settings(client: Client, request: CoreMessage[GetNotifySettings], session_id: int):
    return PeerNotifySettings(
        show_previews=True,
        silent=False,
    )


# noinspection PyUnusedLocal
@handler.on_message(GetDefaultEmojiStatuses)
async def get_default_emoji_statuses(client: Client, request: CoreMessage[GetDefaultEmojiStatuses],
                                     session_id: int):
    return EmojiStatuses(hash=0, statuses=[])
