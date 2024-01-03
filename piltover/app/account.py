import re

from piltover.app.utils import auth_required
from piltover.db.models import User, UserAuthorization
from piltover.exceptions import ErrorRpc
from piltover.server import MessageHandler, Client
from piltover.tl.types import CoreMessage
from piltover.tl_new import PeerNotifySettings, GlobalPrivacySettings, \
    PasswordKdfAlgoSHA256SHA256PBKDF2HMACSHA512iter100000SHA256ModPow, \
    SecurePasswordKdfAlgoSHA512, AccountDaysTTL
from piltover.tl_new.functions.account import UpdateStatus, UpdateProfile, GetNotifySettings, GetDefaultEmojiStatuses, \
    GetContentSettings, GetThemes, GetGlobalPrivacySettings, GetPrivacy, GetPassword, GetContactSignUpNotification, \
    RegisterDevice, GetAccountTTL, GetAuthorizations, UpdateUsername, CheckUsername, RegisterDevice_70
from piltover.tl_new.types.account import EmojiStatuses, Themes, ContentSettings, PrivacyRules, Password, Authorizations

handler = MessageHandler("account")
username_regex = re.compile(r'[a-zA-z0-9_]{5,32}')


def validate_username(username: str) -> None:
    if len(username) not in range(5, 32) or not username_regex.match(username):
        raise ErrorRpc(error_code=400, error_message="USERNAME_INVALID")


# noinspection PyUnusedLocal
@handler.on_message(CheckUsername)
@auth_required
async def check_username(client: Client, request: CoreMessage[CheckUsername], session_id: int, user: User):
    validate_username(request.obj.username)
    if await User.filter(username=request.obj.username).exists():
        raise ErrorRpc(error_code=400, error_message="USERNAME_OCCUPIED")
    return True


# noinspection PyUnusedLocal
@handler.on_message(UpdateUsername)
@auth_required
async def update_username(client: Client, request: CoreMessage[UpdateUsername], session_id: int, user: User):
    validate_username(request.obj.username)
    if (target := await User.get_or_none(username__iexact=request.obj.username)) is not None:
        raise ErrorRpc(error_code=400, error_message="USERNAME_NOT_MODIFIED" if target == user else "USERNAME_OCCUPIED")

    await user.update(username=request.obj.username)
    return user.to_tl(user)


# noinspection PyUnusedLocal
@handler.on_message(GetAuthorizations)
@auth_required
async def get_authorizations(client: Client, request: CoreMessage[GetAuthorizations], session_id: int, user: User):
    authorizations = await UserAuthorization.filter(user=user).select_related("key").all()
    authorizations = [auth.to_tl(current=int(auth.key.id) == client.auth_data.auth_key_id) for auth in authorizations]

    return Authorizations(authorization_ttl_days=15, authorizations=authorizations)


# noinspection PyUnusedLocal
@handler.on_message(GetAccountTTL)
async def get_account_ttl(client: Client, request: CoreMessage[GetAccountTTL], session_id: int):
    return AccountDaysTTL(days=15)


# noinspection PyUnusedLocal
@handler.on_message(RegisterDevice_70)
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
@auth_required
async def update_profile(client: Client, request: CoreMessage[UpdateProfile], session_id: int, user: User):
    updates = {}
    if request.obj.first_name is not None:
        if len(request.obj.first_name) > 128 or not request.obj.first_name:
            raise ErrorRpc(error_code=400, error_message="FIRSTNAME_INVALID")
        updates["first_name"] = request.obj.first_name
    if request.obj.last_name is not None:
        updates["last_name"] = request.obj.last_name[:128]
    if request.obj.about is not None:
        if len(request.obj.about) > 240:
            raise ErrorRpc(error_code=400, error_message="ABOUT_TOO_LONG")
        updates["about"] = request.obj.about

    if updates:
        await user.update(**updates)
    return user.to_tl(user)


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
