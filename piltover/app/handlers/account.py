from datetime import date

from piltover.app.utils.updates_manager import UpdatesManager
from piltover.app.utils.utils import check_password_internal, get_perm_key, validate_username
from piltover.app_config import AppConfig
from piltover.context import request_ctx
from piltover.db.enums import PrivacyRuleValueType, PrivacyRuleKeyType, UserStatus
from piltover.db.models import User, UserAuthorization, Peer, Presence, Username, UserPassword, PrivacyRule
from piltover.db.models.privacy_rule import TL_KEY_TO_PRIVACY_ENUM
from piltover.enums import ReqHandlerFlags
from piltover.exceptions import ErrorRpc
from piltover.session_manager import SessionManager
from piltover.tl import PeerNotifySettings, GlobalPrivacySettings, AccountDaysTTL, EmojiList, AutoDownloadSettings, \
    PasswordKdfAlgoSHA256SHA256PBKDF2HMACSHA512iter100000SHA256ModPow, User as TLUser
from piltover.tl.functions.account import UpdateStatus, UpdateProfile, GetNotifySettings, GetDefaultEmojiStatuses, \
    GetContentSettings, GetThemes, GetGlobalPrivacySettings, GetPrivacy, GetPassword, GetContactSignUpNotification, \
    RegisterDevice, GetAccountTTL, GetAuthorizations, UpdateUsername, CheckUsername, RegisterDevice_70, \
    GetSavedRingtones, GetAutoDownloadSettings, GetDefaultProfilePhotoEmojis, GetWebAuthorizations, SetAccountTTL, \
    SaveAutoDownloadSettings, UpdatePasswordSettings, GetPasswordSettings, SetPrivacy, UpdateBirthday
from piltover.tl.types.account import EmojiStatuses, Themes, ContentSettings, PrivacyRules, Password, Authorizations, \
    SavedRingtones, AutoDownloadSettings as AccAutoDownloadSettings, WebAuthorizations, PasswordSettings
from piltover.tl.types.internal import SetSessionInternalPush
from piltover.utils import gen_safe_prime
from piltover.utils.srp import btoi
from piltover.worker import MessageHandler

handler = MessageHandler("account")


@handler.on_request(CheckUsername)
async def check_username(request: CheckUsername) -> bool:
    request.username = request.username.lower()
    validate_username(request.username)
    if await Username.filter(username=request.username).exists():
        raise ErrorRpc(error_code=400, error_message="USERNAME_OCCUPIED")
    return True


@handler.on_request(UpdateUsername)
async def update_username(request: UpdateUsername, user: User) -> TLUser:
    request.username = request.username.lower().strip()
    current_username = await user.get_username()
    if (not request.username and current_username is None) \
            or (current_username is not None and current_username.username == request.username):
        raise ErrorRpc(error_code=400, error_message="USERNAME_NOT_MODIFIED")

    if request.username:
        validate_username(request.username)
        if await Username.filter(username__iexact=request.username).exists():
            raise ErrorRpc(error_code=400, error_message="USERNAME_OCCUPIED")

    if current_username is not None:
        if not request.username:
            await current_username.delete()
            user.cached_username = None
        else:
            current_username.username = request.username
            await current_username.save(update_fields=["username"])
    else:
        user.cached_username = await Username.create(user=user, username=request.username)

    await UpdatesManager.update_user_name(user)
    return await user.to_tl(user)


@handler.on_request(GetAuthorizations)
async def get_authorizations(user: User):
    current_key = await get_perm_key(request_ctx.get().auth_key_id)
    authorizations = await UserAuthorization.filter(user=user).select_related("key").all()
    authorizations = [auth.to_tl(current=auth.key == current_key) for auth in authorizations]

    return Authorizations(authorization_ttl_days=15, authorizations=authorizations)


@handler.on_request(GetAccountTTL)
async def get_account_ttl(user: User):
    return AccountDaysTTL(days=user.ttl_days)


@handler.on_request(SetAccountTTL)
async def set_account_ttl(request: SetAccountTTL, user: User):
    if request.ttl.days not in range(30, 366):
        raise ErrorRpc(error_code=400, error_message="TTL_DAYS_INVALID")

    user.ttl_days = request.ttl.days
    await user.save(update_fields=["ttl_days"])

    return True


@handler.on_request(RegisterDevice_70)
@handler.on_request(RegisterDevice)
async def register_device(request: RegisterDevice, user: User) -> bool:
    if request.token_type != 7:
        return False
    sess_id = int(request.token)
    key_id = request_ctx.get().auth_key_id

    await SessionManager.broker.send(SetSessionInternalPush(
        key_id=key_id,
        session_id=sess_id,
        user_id=user.id,
    ))

    return True


@handler.on_request(GetContactSignUpNotification)
async def get_contact_sign_up_notification() -> bool:  # pragma: no cover
    return True


@handler.on_request(GetPassword, ReqHandlerFlags.ALLOW_MFA_PENDING)
async def get_password(user: User) -> Password:
    password, _ = await UserPassword.get_or_create(user=user)
    return await password.to_tl()


@handler.on_request(UpdatePasswordSettings)
async def update_password_settings(request: UpdatePasswordSettings, user: User) -> bool:
    password, _ = await UserPassword.get_or_create(user=user)
    await check_password_internal(password, request.password)

    new = request.new_settings

    if not new.new_password_hash:
        if password.password is None:
            raise ErrorRpc(error_code=400, error_message="NEW_SETTINGS_EMPTY")
        password.password = None
        password.hint = None
        password.salt1 = password.salt1[:8]
        await password.save(update_fields=["password", "hint", "salt1"])
        await UserAuthorization.filter(user=user, mfa_pending=True).delete()
        return True

    p, _ = gen_safe_prime()
    if btoi(new.new_password_hash) >= p or len(new.new_password_hash) != 256:
        raise ErrorRpc(error_code=400, error_message="NEW_SETTINGS_INVALID")
    if not isinstance(new.new_algo, PasswordKdfAlgoSHA256SHA256PBKDF2HMACSHA512iter100000SHA256ModPow):
        raise ErrorRpc(error_code=400, error_message="NEW_SETTINGS_INVALID")

    if new.new_algo.salt2 != password.salt2 \
            or new.new_algo.salt1[:8] != password.salt1[:8] \
            or len(new.new_algo.salt1) != 40:
        raise ErrorRpc(error_code=400, error_message="NEW_SALT_INVALID")

    password.password = new.new_password_hash
    password.hint = new.hint
    password.salt1 = new.new_algo.salt1
    await password.save(update_fields=["password", "hint", "salt1"])

    return True


@handler.on_request(GetPasswordSettings)
async def get_password_settings(request: GetPasswordSettings, user: User) -> PasswordSettings:
    password, _ = await UserPassword.get_or_create(user=user)
    await check_password_internal(password, request.password)

    return PasswordSettings()


async def get_privacy_internal(key: PrivacyRuleKeyType, user: User) -> PrivacyRules:
    rules_ = await PrivacyRule.filter(user=user, key=key)
    rules = []
    users = []
    for rule in rules_:
        rules.append(await rule.to_tl())
        if rule.value in {PrivacyRuleValueType.ALLOW_USERS, PrivacyRuleValueType.DISALLOW_USERS}:
            users.extend([await rule_user.to_tl(user) for rule_user in await rule.users.all()])

    return PrivacyRules(
        rules=rules,
        chats=[],
        users=users,
    )


@handler.on_request(GetPrivacy)
async def get_privacy(request: GetPrivacy, user: User):
    return await get_privacy_internal(TL_KEY_TO_PRIVACY_ENUM[type(request.key)], user)


@handler.on_request(SetPrivacy)
async def set_privacy(request: SetPrivacy, user: User):
    key = TL_KEY_TO_PRIVACY_ENUM[type(request.key)]
    await PrivacyRule.update_from_tl(user, key, request.rules)
    await UpdatesManager.update_user(user)
    return await get_privacy_internal(key, user)


@handler.on_request(GetThemes, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_themes():  # pragma: no cover
    return Themes(hash=0, themes=[])


@handler.on_request(GetGlobalPrivacySettings, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_global_privacy_settings():  # pragma: no cover
    return GlobalPrivacySettings(archive_and_mute_new_noncontact_peers=True)


@handler.on_request(GetContentSettings, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_content_settings():  # pragma: no cover
    return ContentSettings(
        sensitive_enabled=True,
        sensitive_can_change=True,
    )


@handler.on_request(UpdateStatus)
async def update_status(request: UpdateStatus, user: User) -> bool:
    presence = await Presence.update_to_now(user, UserStatus.OFFLINE if request.offline else UserStatus.ONLINE)
    await UpdatesManager.update_status(user, presence, await Peer.filter(user=user).select_related("owner"))

    return True


@handler.on_request(UpdateProfile)
async def update_profile(request: UpdateProfile, user: User):
    updates = {}
    if request.first_name is not None:
        if len(request.first_name) > 128 or not request.first_name:
            raise ErrorRpc(error_code=400, error_message="FIRSTNAME_INVALID")
        updates["first_name"] = request.first_name
    if request.last_name is not None:
        updates["last_name"] = request.last_name[:128]
    if request.about is not None:
        if len(request.about) > AppConfig.MAX_USER_ABOUT_LENGTH:
            raise ErrorRpc(error_code=400, error_message="ABOUT_TOO_LONG")
        updates["about"] = request.about

    if updates:
        await user.update_from_dict(updates).save(update_fields=updates.keys())
        if "about" in updates:
            await UpdatesManager.update_user(user)
        else:
            await UpdatesManager.update_user_name(user)

    return await user.to_tl(user)


@handler.on_request(GetNotifySettings, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_notify_settings():  # pragma: no cover
    return PeerNotifySettings(
        show_previews=True,
        silent=False,
    )


@handler.on_request(GetDefaultEmojiStatuses, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_default_emoji_statuses():  # pragma: no cover
    return EmojiStatuses(hash=0, statuses=[])


@handler.on_request(GetSavedRingtones, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_saved_ringtones(request: GetSavedRingtones):  # pragma: no cover
    return SavedRingtones(hash=request.hash, ringtones=[])


@handler.on_request(GetAutoDownloadSettings, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_auto_download_settings():  # pragma: no cover
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


@handler.on_request(SaveAutoDownloadSettings, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def save_auto_download_settings() -> bool:  # pragma: no cover
    """
    It seems like this function is doing nothing on official Telegram server??
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


@handler.on_request(GetDefaultProfilePhotoEmojis, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_default_profile_photo_emojis(request: GetDefaultProfilePhotoEmojis) -> EmojiList:  # pragma: no cover
    return EmojiList(hash=request.hash, document_id=[])


@handler.on_request(GetWebAuthorizations)
async def get_web_authorizations(user: User) -> WebAuthorizations:  # pragma: no cover
    return WebAuthorizations(authorizations=[], users=[await user.to_tl(user)])


@handler.on_request(UpdateBirthday)
async def update_birthday(request: UpdateBirthday, user: User) -> bool:
    before = user.birthday
    after = None
    if request.birthday:
        this_year = date.today().year
        age = this_year - (request.birthday.year if request.birthday.year else this_year)
        if request.birthday.year and (age < 0 or age > 150):
            raise ErrorRpc(error_code=400, error_message="BIRTHDAY_INVALID")

        after = date(
            year=request.birthday.year if request.birthday.year else 1900,
            month=request.birthday.month,
            day=request.birthday.day,
        )

    if before != after:
        user.birthday = after
        await user.save(update_fields=["birthday"])
        await UpdatesManager.update_user(user)

    return True
