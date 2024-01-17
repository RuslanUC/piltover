import re

from piltover.db.models import User, UserAuthorization, SrpSession
from piltover.db.models.user_password import UserPassword
from piltover.exceptions import ErrorRpc
from piltover.high_level import MessageHandler, Client
from piltover.tl_new import PeerNotifySettings, GlobalPrivacySettings, \
    PasswordKdfAlgoSHA256SHA256PBKDF2HMACSHA512iter100000SHA256ModPow, \
    AccountDaysTTL, EmojiList, \
    AutoDownloadSettings, InputCheckPasswordEmpty, InputCheckPasswordSRP
from piltover.tl_new.functions.account import UpdateStatus, UpdateProfile, GetNotifySettings, GetDefaultEmojiStatuses, \
    GetContentSettings, GetThemes, GetGlobalPrivacySettings, GetPrivacy, GetPassword, GetContactSignUpNotification, \
    RegisterDevice, GetAccountTTL, GetAuthorizations, UpdateUsername, CheckUsername, RegisterDevice_70, \
    GetSavedRingtones, GetAutoDownloadSettings, GetDefaultProfilePhotoEmojis, GetWebAuthorizations, SetAccountTTL, \
    SaveAutoDownloadSettings, UpdatePasswordSettings, GetPasswordSettings
from piltover.tl_new.types.account import EmojiStatuses, Themes, ContentSettings, PrivacyRules, Password, \
    Authorizations, SavedRingtones, AutoDownloadSettings as AccAutoDownloadSettings, WebAuthorizations, PasswordSettings
from piltover.utils import gen_safe_prime
from piltover.utils.srp import sha256, xor, itob, btoi

handler = MessageHandler("account")
username_regex = re.compile(r'[a-zA-z0-9_]{5,32}')
username_regex_no_len = re.compile(r'[a-zA-z0-9_]{1,32}')


def validate_username(username: str) -> None:
    if len(username) not in range(5, 32) or not username_regex.match(username):
        raise ErrorRpc(error_code=400, error_message="USERNAME_INVALID")


# noinspection PyUnusedLocal
@handler.on_request(CheckUsername, True)
async def check_username(client: Client, request: CheckUsername, user: User):
    validate_username(request.username)
    if await User.filter(username=request.username).exists():
        raise ErrorRpc(error_code=400, error_message="USERNAME_OCCUPIED")
    return True


# noinspection PyUnusedLocal
@handler.on_request(UpdateUsername, True)
async def update_username(client: Client, request: UpdateUsername, user: User):
    validate_username(request.username)
    if (target := await User.get_or_none(username__iexact=request.username)) is not None:
        raise ErrorRpc(error_code=400, error_message="USERNAME_NOT_MODIFIED" if target == user else "USERNAME_OCCUPIED")

    await user.update(username=request.username)
    return await user.to_tl(user)


# noinspection PyUnusedLocal
@handler.on_request(GetAuthorizations, True)
async def get_authorizations(client: Client, request: GetAuthorizations, user: User):
    authorizations = await UserAuthorization.filter(user=user).select_related("key").all()
    authorizations = [auth.to_tl(current=int(auth.key.id) == client.auth_data.auth_key_id) for auth in authorizations]

    return Authorizations(authorization_ttl_days=15, authorizations=authorizations)


# noinspection PyUnusedLocal
@handler.on_request(GetAccountTTL, True)
async def get_account_ttl(client: Client, request: GetAccountTTL, user: User):
    return AccountDaysTTL(days=user.ttl_days)


# noinspection PyUnusedLocal
@handler.on_request(SetAccountTTL, True)
async def set_account_ttl(client: Client, request: SetAccountTTL, user: User):
    if request.ttl.days not in range(30, 366):
        raise ErrorRpc(error_code=400, error_message="TTL_DAYS_INVALID")
    await user.update(ttl_days=request.ttl.days)
    return True


# noinspection PyUnusedLocal
@handler.on_request(RegisterDevice_70)
@handler.on_request(RegisterDevice)
async def register_device(client: Client, request: RegisterDevice) -> bool:
    print(request)
    return True


# noinspection PyUnusedLocal
@handler.on_request(GetContactSignUpNotification)
async def get_contact_sign_up_notification(client: Client, request: GetContactSignUpNotification) -> bool:
    return True


# noinspection PyUnusedLocal
@handler.on_request(GetPassword, True)
async def get_password(client: Client, request: GetPassword, user: User) -> Password:
    password, _ = await UserPassword.get_or_create(user=user)
    return await password.to_tl()


async def check_password_internal(password: UserPassword, check: InputCheckPasswordEmpty | InputCheckPasswordSRP):
    if password.password is not None and isinstance(check, InputCheckPasswordEmpty):
        raise ErrorRpc(error_code=400, error_message="PASSWORD_HASH_INVALID")

    if password.password is None:
        return

    if (sess := await SrpSession.get_current(password)).id != check.srp_id:
        raise ErrorRpc(error_code=400, error_message="SRP_ID_INVALID")

    p, g = gen_safe_prime()

    u = sha256(check.A + sess.pub_B())
    s_b = pow(btoi(check.A) * pow(btoi(password.password), btoi(u), p), btoi(sess.priv_b), p)
    k_b = sha256(itob(s_b))

    M2 = sha256(
        xor(sha256(itob(p)), sha256(itob(g)))
        + sha256(password.salt1)
        + sha256(password.salt2)
        + check.A
        + sess.pub_B()
        + k_b
    )

    if check.M1 != M2:
        raise ErrorRpc(error_code=400, error_message="PASSWORD_HASH_INVALID")


# noinspection PyUnusedLocal
@handler.on_request(UpdatePasswordSettings, True)
async def update_password_settings(client: Client, request: UpdatePasswordSettings, user: User) -> bool:
    password, _ = await UserPassword.get_or_create(user=user)
    await check_password_internal(password, request.password)

    new = request.new_settings

    if not new.new_password_hash:
        if password.password is None:
            raise ErrorRpc(error_code=400, error_message="NEW_SETTINGS_EMPTY")
        await password.update(password=None, hint=None, salt1=password.salt1[:8])
        return True

    p, _ = gen_safe_prime()
    if btoi(new.new_password_hash) >= p or len(new.new_password_hash) != 256:
        raise ErrorRpc(error_code=400, error_message="NEW_SETTINGS_INVALID")
    if not isinstance(new.new_algo, PasswordKdfAlgoSHA256SHA256PBKDF2HMACSHA512iter100000SHA256ModPow):
        raise ErrorRpc(error_code=400, error_message="NEW_SETTINGS_INVALID")

    if new.new_algo.salt2 != password.salt2 or new.new_algo.salt1[:8] != password.salt1[:8] \
            or len(new.new_algo.salt1) != 40:
        raise ErrorRpc(error_code=400, error_message="NEW_SALT_INVALID")

    await password.update(password=new.new_password_hash, salt1=new.new_algo.salt1, hint=new.hint)
    return True


# noinspection PyUnusedLocal
@handler.on_request(GetPasswordSettings, True)
async def get_password_settings(client: Client, request: GetPasswordSettings, user: User) -> PasswordSettings:
    password, _ = await UserPassword.get_or_create(user=user)
    await check_password_internal(password, request.password)

    return PasswordSettings()


# noinspection PyUnusedLocal
@handler.on_request(GetPrivacy)
async def get_privacy(client: Client, request: GetPrivacy):
    return PrivacyRules(
        rules=[],
        chats=[],
        users=[],
    )


# noinspection PyUnusedLocal
@handler.on_request(GetThemes)
async def get_themes(client: Client, request: GetThemes):
    return Themes(hash=0, themes=[])


# noinspection PyUnusedLocal
@handler.on_request(GetGlobalPrivacySettings)
async def get_global_privacy_settings(client: Client, request: GetGlobalPrivacySettings):
    return GlobalPrivacySettings(archive_and_mute_new_noncontact_peers=True)


# noinspection PyUnusedLocal
@handler.on_request(GetContentSettings)
async def get_content_settings(client: Client, request: GetContentSettings):
    return ContentSettings(
        sensitive_enabled=True,
        sensitive_can_change=True,
    )


# noinspection PyUnusedLocal
@handler.on_request(UpdateStatus)
async def update_status(client: Client, request: UpdateStatus):
    return True


# noinspection PyUnusedLocal
@handler.on_request(UpdateProfile, True)
async def update_profile(client: Client, request: UpdateProfile, user: User):
    updates = {}
    if request.first_name is not None:
        if len(request.first_name) > 128 or not request.first_name:
            raise ErrorRpc(error_code=400, error_message="FIRSTNAME_INVALID")
        updates["first_name"] = request.first_name
    if request.last_name is not None:
        updates["last_name"] = request.last_name[:128]
    if request.about is not None:
        if len(request.about) > 240:
            raise ErrorRpc(error_code=400, error_message="ABOUT_TOO_LONG")
        updates["about"] = request.about

    if updates:
        await user.update(**updates)
    return await user.to_tl(user)


# noinspection PyUnusedLocal
@handler.on_request(GetNotifySettings)
async def get_notify_settings(client: Client, request: GetNotifySettings):
    return PeerNotifySettings(
        show_previews=True,
        silent=False,
    )


# noinspection PyUnusedLocal
@handler.on_request(GetDefaultEmojiStatuses)
async def get_default_emoji_statuses(client: Client, request: GetDefaultEmojiStatuses):
    return EmojiStatuses(hash=0, statuses=[])


# noinspection PyUnusedLocal
@handler.on_request(GetSavedRingtones)
async def get_saved_ringtones(client: Client, request: GetSavedRingtones):
    return SavedRingtones(hash=request.hash, ringtones=[])


# noinspection PyUnusedLocal
@handler.on_request(GetAutoDownloadSettings)
async def get_auto_download_settings(client: Client, request: GetAutoDownloadSettings):
    return AccAutoDownloadSettings(
        low=AutoDownloadSettings(
            disabled=False,
            audio_preload_next=False,
            phonecalls_less_data=True,
            photo_size_max=1048576,
            video_size_max=0,
            file_size_max=0,
            video_upload_maxbitrate=50,
            small_queue_active_operations_max=0,
            large_queue_active_operations_max=0,
        ),
        medium=AutoDownloadSettings(
            disabled=False,
            audio_preload_next=True,
            phonecalls_less_data=False,
            photo_size_max=1048576,
            video_size_max=10485760,
            file_size_max=1048576,
            video_upload_maxbitrate=100,
            small_queue_active_operations_max=0,
            large_queue_active_operations_max=0,
        ),
        high=AutoDownloadSettings(
            disabled=False,
            audio_preload_next=True,
            phonecalls_less_data=False,
            photo_size_max=1048576,
            video_size_max=15728640,
            file_size_max=3145728,
            video_upload_maxbitrate=100,
            small_queue_active_operations_max=0,
            large_queue_active_operations_max=0,
        ),
    )


# noinspection PyUnusedLocal
@handler.on_request(SaveAutoDownloadSettings)
async def get_auto_download_settings(client: Client, request: SaveAutoDownloadSettings):
    """
    TODO: Seems like this function is doing nothing on official Telegram server??
    Code used to test it:

    settings_before = app.invoke(GetAutoDownloadSettings())
    res = app.invoke(SaveAutoDownloadSettings(
        settings=AutoDownloadSettings(
            photo_size_max=1048577,
            video_size_max=0,
            file_size_max=0,
            video_upload_maxbitrate=50,
            disabled=True,
        ),
        low=True,
        high=True,
    ))
    assert res  # Always True
    settings_after = app.invoke(GetAutoDownloadSettings())
    print(settings_before == settings_after)  # Always True
    assert settings_before == settings_after
    """
    return True


# noinspection PyUnusedLocal
@handler.on_request(GetDefaultProfilePhotoEmojis)
async def get_default_profile_photo_emojis(client: Client, request: GetDefaultProfilePhotoEmojis):
    return EmojiList(hash=request.hash, document_id=[])


# noinspection PyUnusedLocal
@handler.on_request(GetWebAuthorizations, True)
async def get_web_authorizations(client: Client, request: GetWebAuthorizations, user: User):
    return WebAuthorizations(authorizations=[], users=await user.to_tl(user))
