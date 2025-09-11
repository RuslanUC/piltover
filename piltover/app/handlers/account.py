from datetime import date, timedelta, datetime

from pytz import UTC

import piltover.app.utils.updates_manager as upd
from piltover.app.utils.utils import check_password_internal, get_perm_key, validate_username
from piltover.app_config import AppConfig
from piltover.context import request_ctx
from piltover.db.enums import PrivacyRuleValueType, PrivacyRuleKeyType, UserStatus, PushTokenType
from piltover.db.models import User, UserAuthorization, Peer, Presence, Username, UserPassword, PrivacyRule, \
    UserPasswordReset, SentCode, PhoneCodePurpose
from piltover.db.models.privacy_rule import TL_KEY_TO_PRIVACY_ENUM
from piltover.enums import ReqHandlerFlags
from piltover.exceptions import ErrorRpc
from piltover.session_manager import SessionManager
from piltover.tl import PeerNotifySettings, GlobalPrivacySettings, AccountDaysTTL, EmojiList, AutoDownloadSettings, \
    PasswordKdfAlgoSHA256SHA256PBKDF2HMACSHA512iter100000SHA256ModPow, User as TLUser, Long, UpdatesTooLong
from piltover.tl.base.account import ResetPasswordResult
from piltover.tl.functions.account import UpdateStatus, UpdateProfile, GetNotifySettings, GetDefaultEmojiStatuses, \
    GetContentSettings, GetThemes, GetGlobalPrivacySettings, GetPrivacy, GetPassword, GetContactSignUpNotification, \
    RegisterDevice, GetAccountTTL, GetAuthorizations, UpdateUsername, CheckUsername, RegisterDevice_70, \
    GetSavedRingtones, GetAutoDownloadSettings, GetDefaultProfilePhotoEmojis, GetWebAuthorizations, SetAccountTTL, \
    SaveAutoDownloadSettings, UpdatePasswordSettings, GetPasswordSettings, SetPrivacy, UpdateBirthday, \
    ChangeAuthorizationSettings, ResetAuthorization, ResetPassword, DeclinePasswordReset, SendChangePhoneCode, \
    SendConfirmPhoneCode, ChangePhone, DeleteAccount
from piltover.tl.types.account import EmojiStatuses, Themes, ContentSettings, PrivacyRules, Password, Authorizations, \
    SavedRingtones, AutoDownloadSettings as AccAutoDownloadSettings, WebAuthorizations, PasswordSettings, \
    ResetPasswordOk, ResetPasswordRequestedWait
from piltover.tl.types.auth import SentCode as TLSentCode, SentCodeTypeSms
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

    await upd.update_user_name(user)
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
    if request.token_type not in PushTokenType._value2member_map_:
        return False

    token_type = PushTokenType(request.token_type)

    if token_type is not PushTokenType.INTERNAL:
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
        await UserPasswordReset.filter(user=user).delete()
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
    await UserPasswordReset.filter(user=user).delete()

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
    await upd.update_user(user)
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
    await upd.update_status(user, presence, await Peer.filter(user=user).select_related("owner"))

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
            await upd.update_user(user)
        else:
            await upd.update_user_name(user)

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
        await upd.update_user(user)

    return True


@handler.on_request(ChangeAuthorizationSettings)
async def change_auth_settings(request: ChangeAuthorizationSettings, user: User) -> bool:
    auth_id = request_ctx.get().auth_id
    this_auth = await UserAuthorization.get_or_none(id=auth_id)

    auth_hash_hex = Long.write(request.hash).hex()
    auth = await UserAuthorization.get_or_none(user=user, hash__startswith=auth_hash_hex)
    if auth is None or auth == this_auth or this_auth.created_at > auth.created_at:
        raise ErrorRpc(error_code=400, error_message="HASH_INVALID")

    to_update = []
    if not auth.confirmed and request.confirmed:
        auth.confirmed = True
        to_update.append("confirmed")

    if request.encrypted_requests_disabled is not None \
            and auth.allow_encrypted_requests != (not request.encrypted_requests_disabled):
        auth.allow_encrypted_requests = not request.encrypted_requests_disabled
        to_update.append("allow_encrypted_requests")

    if request.call_requests_disabled is not None \
            and auth.allow_call_requests != (not request.call_requests_disabled):
        auth.allow_call_requests = not request.call_requests_disabled
        to_update.append("allow_call_requests")

    if not to_update:
        return True

    await auth.save(update_fields=to_update)

    return True


@handler.on_request(ResetAuthorization)
async def reset_authorization(request: ResetAuthorization, user: User) -> bool:
    auth_id = request_ctx.get().auth_id
    this_auth = await UserAuthorization.get_or_none(id=auth_id)

    if (this_auth.created_at + timedelta(days=1)) > datetime.now(UTC):
        raise ErrorRpc(error_code=406, error_message="FRESH_RESET_AUTHORISATION_FORBIDDEN")

    auth_hash_hex = Long.write(request.hash).hex()
    auth = await UserAuthorization.get_or_none(user=user, hash__startswith=auth_hash_hex).select_related("key")
    if auth is None or auth == this_auth:
        raise ErrorRpc(error_code=400, error_message="HASH_INVALID")

    keys = await auth.key.get_ids()
    await auth.delete()

    await SessionManager.send(UpdatesTooLong(), key_id=keys)

    return True


@handler.on_request(ResetPassword)
async def reset_password(user: User) -> ResetPasswordResult:
    if (password := await UserPassword.get_or_none(user=user)) is None:
        raise ErrorRpc(error_code=400, error_message="PASSWORD_EMPTY")

    reset_request, created = await UserPasswordReset.get_or_create(user=user)
    reset_date = reset_request.date + timedelta(seconds=AppConfig.SRP_PASSWORD_RESET_WAIT_SECONDS)
    if datetime.now() > reset_date:
        await password.delete()
        await reset_request.delete()
        return ResetPasswordOk()

    return ResetPasswordRequestedWait(until_date=int(reset_date.timestamp()))


@handler.on_request(DeclinePasswordReset)
async def decline_password_reset(user: User) -> bool:
    if (reset_request := await UserPasswordReset.get_or_none(user=user)) is None:
        raise ErrorRpc(error_code=400, error_message="RESET_REQUEST_MISSING")

    await reset_request.delete()

    return True


async def _create_sent_code(user: User, phone_number: str, purpose: PhoneCodePurpose) -> TLSentCode:
    try:
        if int(phone_number) < 100000:
            raise ValueError
    except ValueError:
        raise ErrorRpc(error_code=406, error_message="PHONE_NUMBER_INVALID")

    if await User.filter(phone_number=phone_number).exists():
        raise ErrorRpc(error_code=400, error_message="PHONE_NUMBER_OCCUPIED")

    code = await SentCode.create(
        phone_number=int(phone_number),
        purpose=purpose,
        user=user,
    )

    return TLSentCode(
        type_=SentCodeTypeSms(length=5),
        phone_code_hash=code.phone_code_hash(),
        timeout=30,
    )


@handler.on_request(SendChangePhoneCode)
async def send_change_phone_code(request: SendChangePhoneCode, user: User) -> TLSentCode:
    return await _create_sent_code(user, request.phone_number, PhoneCodePurpose.CHANGE_NUMBER)


@handler.on_request(ChangePhone)
async def change_phone(request: ChangePhone, user: User) -> TLUser:
    code = await SentCode.get_(request.phone_number, request.phone_code_hash, PhoneCodePurpose.CHANGE_NUMBER)
    await SentCode.check_raise_cls(code, request.phone_code)

    code.used = True
    await code.save(update_fields=["used"])

    if await User.filter(phone_number=request.phone_number).exists():
        raise ErrorRpc(error_code=400, error_message="PHONE_NUMBER_OCCUPIED")

    user.phone_number = request.phone_number
    await user.save(update_fields=["phone_number"])

    # TODO: UpdateUserPhone

    return await user.to_tl(user)

# https://core.telegram.org/api/account-deletion
#@handler.on_request(SendConfirmPhoneCode)
#async def send_confirm_phone_code(request: SendConfirmPhoneCode, user: User) -> TLSentCode:
#    return await _create_sent_code(user, request.phone_number, PhoneCodePurpose.DELETE_ACCOUNT)
# TODO: ConfirmPhone


async def _delete_account(user: User) -> None:
    user.deleted = True
    user.phone_number = None
    user.first_name = ""
    user.last_name = None
    user.about = None
    user.birthday = None
    await user.save(update_fields=["deleted", "phone_number", "first_name", "last_name", "about", "birthday"])

    auths = await UserAuthorization.get_or_none(user=user).select_related("key")

    auth_ids = []
    keys = []
    for auth in auths:
        keys.extend(await auth.key.get_ids())
        auth_ids.append(auth.id)

    await UserAuthorization.filter(id__in=auth_ids).delete()

    await SessionManager.send(UpdatesTooLong(), key_id=keys, auth_id=auth_ids)

    # TODO: send UpdateUser to related peers ?


@handler.on_request(DeleteAccount)
async def delete_account(request: DeleteAccount, user: User) -> bool:
    password = await UserPassword.get_or_none(user=user)
    if password is None or password.password is None:
        await _delete_account(user)
        return True

    if (datetime.now(UTC) - timedelta(days=7)) > password.modified_at:
        await _delete_account(user)
        return True
    elif request.password is not None:
        await check_password_internal(password, request.password)
        await _delete_account(user)
        return True

    # TODO: schedule deletion and send service message
    one_week = 86400 * 7
    raise ErrorRpc(error_code=420, error_message=f"2FA_CONFIRM_WAIT_{one_week}")


