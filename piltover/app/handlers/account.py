from base64 import urlsafe_b64encode
from datetime import date, timedelta, datetime
from os import urandom

from pytz import UTC
from tortoise.expressions import Q

import piltover.app.utils.updates_manager as upd
from piltover.app.handlers.auth import _validate_phone
from piltover.app.utils.utils import check_password_internal, validate_username, telegram_hash
from piltover.app_config import AppConfig
from piltover.context import request_ctx
from piltover.db.enums import PrivacyRuleKeyType, UserStatus, PushTokenType, PeerType
from piltover.db.models import User, UserAuthorization, Peer, Presence, Username, UserPassword, PrivacyRule, \
    UserPasswordReset, SentCode, PhoneCodePurpose, Theme, UploadingFile, Wallpaper, WallpaperSettings, \
    InstalledWallpaper, PeerColorOption, UserPersonalChannel, PeerNotifySettings, File, UserBackgroundEmojis
from piltover.enums import ReqHandlerFlags
from piltover.exceptions import ErrorRpc
from piltover.session_manager import SessionManager
from piltover.tl import PeerNotifySettings as TLPeerNotifySettings, GlobalPrivacySettings, AccountDaysTTL, EmojiList, \
    AutoDownloadSettings, PasswordKdfAlgoSHA256SHA256PBKDF2HMACSHA512iter100000SHA256ModPow, User as TLUser, Long, \
    UpdatesTooLong, WallPaper, DocumentAttributeFilename, TLObjectVector, InputWallPaperNoFile, InputChannelEmpty, \
    EmojiListNotModified, PrivacyValueDisallowAll
from piltover.tl.base.account import ResetPasswordResult
from piltover.tl.functions.account import UpdateStatus, UpdateProfile, GetNotifySettings, GetDefaultEmojiStatuses, \
    GetContentSettings, GetThemes, GetGlobalPrivacySettings, GetPrivacy, GetPassword, GetContactSignUpNotification, \
    RegisterDevice, GetAccountTTL, GetAuthorizations, UpdateUsername, CheckUsername, RegisterDevice_70, \
    GetSavedRingtones, GetAutoDownloadSettings, GetDefaultProfilePhotoEmojis, GetWebAuthorizations, SetAccountTTL, \
    SaveAutoDownloadSettings, UpdatePasswordSettings, GetPasswordSettings, SetPrivacy, UpdateBirthday, \
    ChangeAuthorizationSettings, ResetAuthorization, ResetPassword, DeclinePasswordReset, SendChangePhoneCode, \
    ChangePhone, DeleteAccount, GetChatThemes, UploadWallPaper_133, UploadWallPaper, GetWallPaper, GetMultiWallPapers, \
    SaveWallPaper, InstallWallPaper, GetWallPapers, ResetWallPapers, UpdateColor, GetDefaultBackgroundEmojis, \
    UpdatePersonalChannel, UpdateNotifySettings, SetGlobalPrivacySettings
from piltover.tl.types.account import EmojiStatuses, Themes, ContentSettings, PrivacyRules, Password, Authorizations, \
    SavedRingtones, AutoDownloadSettings as AccAutoDownloadSettings, WebAuthorizations, PasswordSettings, \
    ResetPasswordOk, ResetPasswordRequestedWait, ThemesNotModified, WallPapersNotModified, WallPapers
from piltover.tl.types.auth import SentCode as TLSentCode, SentCodeTypeSms
from piltover.tl.types.internal import SetSessionInternalPush
from piltover.utils import gen_safe_prime
from piltover.utils.srp import btoi
from piltover.utils.users_chats_channels import UsersChatsChannels
from piltover.worker import MessageHandler

handler = MessageHandler("account")


@handler.on_request(CheckUsername, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def check_username(request: CheckUsername) -> bool:
    request.username = request.username.lower()
    validate_username(request.username)
    if await Username.filter(username=request.username).exists():
        raise ErrorRpc(error_code=400, error_message="USERNAME_OCCUPIED")
    return True


@handler.on_request(UpdateUsername, ReqHandlerFlags.BOT_NOT_ALLOWED)
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


@handler.on_request(GetAuthorizations, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def get_authorizations(user: User):
    current_key_id = request_ctx.get().perm_auth_key_id
    authorizations = await UserAuthorization.filter(user=user).all()
    authorizations = [auth.to_tl(current=auth.key_id == current_key_id) for auth in authorizations]

    return Authorizations(authorization_ttl_days=15, authorizations=authorizations)


@handler.on_request(GetAccountTTL, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def get_account_ttl(user: User):
    return AccountDaysTTL(days=user.ttl_days)


@handler.on_request(SetAccountTTL, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def set_account_ttl(request: SetAccountTTL, user: User):
    if request.ttl.days not in range(30, 366):
        raise ErrorRpc(error_code=400, error_message="TTL_DAYS_INVALID")

    user.ttl_days = request.ttl.days
    await user.save(update_fields=["ttl_days"])

    return True


@handler.on_request(RegisterDevice_70, ReqHandlerFlags.BOT_NOT_ALLOWED)
@handler.on_request(RegisterDevice, ReqHandlerFlags.BOT_NOT_ALLOWED)
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


@handler.on_request(GetContactSignUpNotification, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def get_contact_sign_up_notification() -> bool:  # pragma: no cover
    return True


@handler.on_request(GetPassword, ReqHandlerFlags.ALLOW_MFA_PENDING | ReqHandlerFlags.BOT_NOT_ALLOWED)
async def get_password(user: User) -> Password:
    password, _ = await UserPassword.get_or_create(user=user)
    return await password.to_tl()


@handler.on_request(UpdatePasswordSettings, ReqHandlerFlags.BOT_NOT_ALLOWED)
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
    password.modified_at = datetime.now(UTC)
    await password.save(update_fields=["password", "hint", "salt1", "modified_at"])
    await UserPasswordReset.filter(user=user).delete()

    return True


@handler.on_request(GetPasswordSettings, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def get_password_settings(request: GetPasswordSettings, user: User) -> PasswordSettings:
    password, _ = await UserPassword.get_or_create(user=user)
    await check_password_internal(password, request.password)

    return PasswordSettings()


async def get_privacy_internal(key: PrivacyRuleKeyType, user: User) -> PrivacyRules:
    rule = await PrivacyRule.get_or_none(user=user, key=key).prefetch_related("exceptions")
    if rule is None:
        return PrivacyRules(
            rules=[PrivacyValueDisallowAll()],
            chats=[],
            users=[],
        )

    # TODO: probably it is possible to not use UCC here (just prefetch exceptions__user)
    ucc = UsersChatsChannels()

    for exc in rule.exceptions:
        if exc.user_id is not None:
            ucc.add_user(exc.user_id)

    users, chats, channels = await ucc.resolve(user)

    return PrivacyRules(
        rules=await rule.to_tl_rules(),
        chats=[*chats, *channels],
        users=users,
    )


@handler.on_request(GetPrivacy, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def get_privacy(request: GetPrivacy, user: User) -> PrivacyRules:
    return await get_privacy_internal(PrivacyRuleKeyType.from_tl(request.key), user)


@handler.on_request(SetPrivacy, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def set_privacy(request: SetPrivacy, user: User) -> PrivacyRules:
    # NOTE: official telegram limit is 1000
    if len(request.rules) > 100:
        raise ErrorRpc(error_code=400, error_message="PRIVACY_TOO_LONG")

    key = PrivacyRuleKeyType.from_tl(request.key)
    rule = await PrivacyRule.update_from_tl(user, key, request.rules)

    rules = await get_privacy_internal(key, user)

    await upd.update_privacy(user, rule, rules)
    await upd.update_user(user)

    return rules


@handler.on_request(GetThemes, ReqHandlerFlags.AUTH_NOT_REQUIRED | ReqHandlerFlags.BOT_NOT_ALLOWED)
async def get_themes() -> Themes:  # pragma: no cover
    return Themes(hash=0, themes=[])


@handler.on_request(GetGlobalPrivacySettings, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def get_global_privacy_settings(user: User) -> GlobalPrivacySettings:
    return GlobalPrivacySettings(
        archive_and_mute_new_noncontact_peers=True,
        hide_read_marks=user.read_dates_private,
    )


@handler.on_request(SetGlobalPrivacySettings, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def set_global_privacy_settings(request: SetGlobalPrivacySettings, user: User):
    if user.read_dates_private != request.settings.hide_read_marks:
        user.read_dates_private = request.settings.hide_read_marks
        await user.save(update_fields=["read_dates_private"])

    return await get_global_privacy_settings(user)


@handler.on_request(GetContentSettings, ReqHandlerFlags.AUTH_NOT_REQUIRED | ReqHandlerFlags.BOT_NOT_ALLOWED)
async def get_content_settings():  # pragma: no cover
    return ContentSettings(
        sensitive_enabled=True,
        sensitive_can_change=True,
    )


@handler.on_request(UpdateStatus, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def update_status(request: UpdateStatus, user: User) -> bool:
    presence = await Presence.update_to_now(user, UserStatus.OFFLINE if request.offline else UserStatus.ONLINE)
    await upd.update_status(user, presence, await Peer.filter(user=user).select_related("owner"))

    return True


@handler.on_request(UpdateProfile, ReqHandlerFlags.BOT_NOT_ALLOWED)
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


@handler.on_request(GetNotifySettings, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def get_notify_settings(request: GetNotifySettings, user: User) -> TLPeerNotifySettings:
    peer, not_peer = await PeerNotifySettings.peer_from_tl(user, request.peer)
    settings, _ = await PeerNotifySettings.get_or_create(user=user, peer=peer, not_peer=not_peer)

    return settings.to_tl()


@handler.on_request(GetDefaultEmojiStatuses, ReqHandlerFlags.AUTH_NOT_REQUIRED | ReqHandlerFlags.BOT_NOT_ALLOWED)
async def get_default_emoji_statuses():  # pragma: no cover
    return EmojiStatuses(hash=0, statuses=[])


@handler.on_request(GetSavedRingtones, ReqHandlerFlags.AUTH_NOT_REQUIRED | ReqHandlerFlags.BOT_NOT_ALLOWED)
async def get_saved_ringtones(request: GetSavedRingtones):  # pragma: no cover
    return SavedRingtones(hash=request.hash, ringtones=[])


@handler.on_request(GetAutoDownloadSettings, ReqHandlerFlags.AUTH_NOT_REQUIRED | ReqHandlerFlags.BOT_NOT_ALLOWED)
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


@handler.on_request(SaveAutoDownloadSettings, ReqHandlerFlags.AUTH_NOT_REQUIRED | ReqHandlerFlags.BOT_NOT_ALLOWED)
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


@handler.on_request(GetDefaultProfilePhotoEmojis, ReqHandlerFlags.AUTH_NOT_REQUIRED | ReqHandlerFlags.BOT_NOT_ALLOWED)
async def get_default_profile_photo_emojis(request: GetDefaultProfilePhotoEmojis) -> EmojiList:  # pragma: no cover
    return EmojiList(hash=request.hash, document_id=[])


@handler.on_request(GetWebAuthorizations, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def get_web_authorizations(user: User) -> WebAuthorizations:  # pragma: no cover
    return WebAuthorizations(authorizations=[], users=[await user.to_tl(user)])


@handler.on_request(UpdateBirthday, ReqHandlerFlags.BOT_NOT_ALLOWED)
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


@handler.on_request(ChangeAuthorizationSettings, ReqHandlerFlags.BOT_NOT_ALLOWED)
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


@handler.on_request(ResetAuthorization, ReqHandlerFlags.BOT_NOT_ALLOWED)
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


@handler.on_request(ResetPassword, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def reset_password(user: User) -> ResetPasswordResult:
    if (password := await UserPassword.get_or_none(user=user)) is None:
        raise ErrorRpc(error_code=400, error_message="PASSWORD_EMPTY")

    reset_request, created = await UserPasswordReset.get_or_create(user=user)
    reset_date = reset_request.date + timedelta(seconds=AppConfig.SRP_PASSWORD_RESET_WAIT_SECONDS)
    if datetime.now(UTC) > reset_date:
        await password.delete()
        await reset_request.delete()
        return ResetPasswordOk()

    return ResetPasswordRequestedWait(until_date=int(reset_date.timestamp()))


@handler.on_request(DeclinePasswordReset, ReqHandlerFlags.BOT_NOT_ALLOWED)
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

    print(f"Code: {code.code}")

    return TLSentCode(
        type_=SentCodeTypeSms(length=5),
        phone_code_hash=code.phone_code_hash(),
        timeout=30,
    )


@handler.on_request(SendChangePhoneCode, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def send_change_phone_code(request: SendChangePhoneCode, user: User) -> TLSentCode:
    return await _create_sent_code(user, request.phone_number, PhoneCodePurpose.CHANGE_NUMBER)


@handler.on_request(ChangePhone, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def change_phone(request: ChangePhone, user: User) -> TLUser:
    phone_number = _validate_phone(request.phone_number)
    code = await SentCode.get_(phone_number, request.phone_code_hash, PhoneCodePurpose.CHANGE_NUMBER)
    await SentCode.check_raise_cls(code, request.phone_code)

    code.used = True
    await code.save(update_fields=["used"])

    if await User.filter(phone_number=request.phone_number).exists():
        raise ErrorRpc(error_code=400, error_message="PHONE_NUMBER_OCCUPIED")

    user.phone_number = request.phone_number
    await user.save(update_fields=["phone_number"])

    await upd.update_user_phone(user)
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


@handler.on_request(DeleteAccount, ReqHandlerFlags.BOT_NOT_ALLOWED)
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


@handler.on_request(GetChatThemes, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def get_chat_themes(request: GetChatThemes, user: User) -> Themes | ThemesNotModified:
    query = Theme.filter(creator=None).order_by("id")
    ids = await query.values_list("id", flat=True)

    themes_hash = telegram_hash(ids, 64)
    if themes_hash == request.hash:
        return ThemesNotModified()

    return Themes(
        hash=themes_hash,
        themes=[
            await theme.to_tl()
            for theme in await query.select_related("document")
        ]
    )


@handler.on_request(UploadWallPaper_133, ReqHandlerFlags.BOT_NOT_ALLOWED)
@handler.on_request(UploadWallPaper, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def upload_wallpaper(request: UploadWallPaper | UploadWallPaper_133, user: User) -> WallPaper:
    attributes = []
    if request.file.name:
        attributes.append(DocumentAttributeFilename(file_name=request.file.name))

    if not request.mime_type.startswith("image/"):
        raise ErrorRpc(error_code=400, error_message="WALLPAPER_MIME_INVALID")

    uploaded_file = await UploadingFile.get_or_none(user=user, file_id=request.file.id)
    if uploaded_file is None:
        raise ErrorRpc(error_code=400, error_message="WALLPAPER_FILE_INVALID")
    if uploaded_file.mime is None or not uploaded_file.mime.startswith("image/"):
        raise ErrorRpc(error_code=400, error_message="WALLPAPER_MIME_INVALID")
    storage = request_ctx.get().storage
    file = await uploaded_file.finalize_upload(storage, request.mime_type, attributes, request.file.parts)

    settings = await WallpaperSettings.create(
        blur=request.settings.blur,
        motion=request.settings.motion,
    )
    wallpaper = await Wallpaper.create(
        creator=user,
        slug=urlsafe_b64encode(urandom(32)).decode("utf8"),
        pattern=False,
        dark=False,
        document=file,
        settings=settings,
    )

    return wallpaper.to_tl()


@handler.on_request(GetWallPaper, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def get_wallpaper(request: GetWallPaper, user: User) -> WallPaper:
    wallpaper = await Wallpaper.from_input(request.wallpaper)
    if wallpaper is None:
        raise ErrorRpc(error_code=400, error_message="WALLPAPER_INVALID")
    return wallpaper.to_tl()


@handler.on_request(GetMultiWallPapers, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def get_multi_wallpapers(request: GetMultiWallPapers, user: User) -> TLObjectVector[WallPaper]:
    if not request.wallpapers:
        return TLObjectVector()

    query = Q()
    for wp in request.wallpapers:
        if (q := Wallpaper.from_input_q(wp, user)) is None:
            raise ErrorRpc(error_code=400, error_message="WALLPAPER_INVALID")
        query &= q

    return TLObjectVector([
        wallpaper.to_tl()
        for wallpaper in await Wallpaper.filter(query).select_related("document", "settings")
    ])


@handler.on_request(SaveWallPaper, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def save_wallpaper(request: SaveWallPaper, user: User) -> bool:
    if isinstance(request.wallpaper, InputWallPaperNoFile):
        raise ErrorRpc(error_code=400, error_message="WALLPAPER_INVALID")

    wallpaper = await Wallpaper.from_input(request.wallpaper)
    if wallpaper is None:
        raise ErrorRpc(error_code=400, error_message="WALLPAPER_INVALID")

    installed = await InstalledWallpaper.get_or_none(user=user, wallpaper=wallpaper).select_related("settings")
    if request.unsave:
        await installed.delete()
        return True

    if installed is None:
        if wallpaper.document is not None:
            settings = await WallpaperSettings.create(
                blur=request.settings.blur,
                motion=request.settings.motion,
            )
        else:
            settings = await WallpaperSettings.create(
                motion=request.settings.motion,
                background_color=request.settings.background_color,
                second_background_color=request.settings.second_background_color,
                third_background_color=request.settings.third_background_color,
                fourth_background_color=request.settings.fourth_background_color,
                intensity=request.settings.intensity,
                rotation=request.settings.rotation,
                emoticon=request.settings.emoticon,
            )
        await InstalledWallpaper.create(user=user, wallpaper=wallpaper, settings=settings)
    else:
        if installed.settings.to_tl() != request.settings:
            if wallpaper.document is not None:
                installed.settings.blur = request.settings.blur
                installed.settings.motion = request.settings.motion
            else:
                installed.settings.motion = request.settings.motion
                installed.settings.background_color = request.settings.background_color
                installed.settings.second_background_color = request.settings.second_background_color
                installed.settings.third_background_color = request.settings.third_background_color
                installed.settings.fourth_background_color = request.settings.fourth_background_color
                installed.settings.intensity = request.settings.intensity
                installed.settings.rotation = request.settings.rotation
                installed.settings.emoticon = request.settings.emoticon
            await installed.settings.save()

    return True


@handler.on_request(InstallWallPaper, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def install_wallpaper(request: InstallWallPaper, user: User) -> bool:
    return await save_wallpaper(
        request=SaveWallPaper(
            wallpaper=request.wallpaper,
            unsave=False,
            settings=request.settings,
        ),
        user=user,
    )


@handler.on_request(GetWallPapers, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def get_wallpapers(request: GetWallPapers, user: User) -> WallPapers | WallPapersNotModified:
    query = InstalledWallpaper.filter(user=user).order_by("id")
    ids = await query.values_list("id", flat=True)

    wallpapers_hash = telegram_hash(ids, 64)
    if wallpapers_hash == request.hash:
        return WallPapersNotModified()

    return WallPapers(
        hash=wallpapers_hash,
        wallpapers=[
            installed.wallpaper.to_tl(installed.settings)
            for installed in await query.select_related("wallpaper", "wallpaper__document", "settings")
        ]
    )


@handler.on_request(ResetWallPapers, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def reset_wallpapers(user: User) -> bool:
    await InstalledWallpaper.filter(user=user).delete()
    return True


@handler.on_request(UpdateColor, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def update_color(request: UpdateColor, user: User) -> bool:
    changed = []

    if request.color is None and request.for_profile and user.profile_color_id is not None:
        user.profile_color = None
        changed.append("profile_color_id")
    elif request.color is None and not request.for_profile and user.accent_color_id is not None:
        user.accent_color = None
        changed.append("accent_color_id")
    elif request.color is not None:
        if (peer_color := await PeerColorOption.get_or_none(id=request.color, is_profile=request.for_profile)) is None:
            raise ErrorRpc(error_code=400, error_message="COLOR_INVALID")
        if request.for_profile:
            user.profile_color = peer_color
            changed.append("profile_color_id")
        else:
            user.accent_color = peer_color
            changed.append("accent_color_id")

    profile_emoji = None
    accent_emoji = None

    if request.background_emoji_id is not None:
        emoji = await File.get_or_none(id=request.background_emoji_id, stickerset__installedstickersets__user=user)
        if emoji is None:
            raise ErrorRpc(error_code=400, error_message="DOCUMENT_INVALID")
        if request.for_profile:
            profile_emoji = emoji
        else:
            accent_emoji = emoji

    if changed:
        await user.save(update_fields=changed)
    if profile_emoji is None and accent_emoji is None:
        await UserBackgroundEmojis.filter(user=user).delete()
    else:
        await UserBackgroundEmojis.update_or_create(user=user, defaults={
            "profile_emoji": profile_emoji,
            "accent_emoji": accent_emoji,
        })

    await upd.update_user(user)
    return True


@handler.on_request(GetDefaultBackgroundEmojis, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def get_default_background_emojis(
        request: GetDefaultBackgroundEmojis, user: User,
) -> EmojiList | EmojiListNotModified:
    ids = await File.filter(
        stickerset__installedstickersets__user=user,
    ).order_by("-stickerset__installedstickersets__installed_at", "id").values_list("id", flat=True)

    emojis_hash = telegram_hash(ids, 64)
    if emojis_hash == request.hash:
        return EmojiListNotModified()

    return EmojiList(hash=emojis_hash, document_id=ids)


@handler.on_request(UpdatePersonalChannel, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def update_personal_channel(request: UpdatePersonalChannel, user: User) -> bool:
    if isinstance(request.channel, InputChannelEmpty):
        personal_channel = await UserPersonalChannel.get_or_none(user=user)
        if personal_channel is not None:
            await personal_channel.delete()
        return True

    peer = await Peer.from_input_peer_raise(
        user, request.channel, message="CHANNEL_PRIVATE", code=406, peer_types=(PeerType.CHANNEL,),
    )

    if peer.channel.creator_id != user.id:
        raise ErrorRpc(error_code=400, error_message="USER_CREATOR")

    if not await Username.filter(channel=peer.channel).exists():
        raise ErrorRpc(error_code=400, error_message="CHANNEL_INVALID")

    await UserPersonalChannel.update_or_create(user=user, defaults={"channel": peer.channel})

    await upd.update_user(user)
    return True


@handler.on_request(UpdateNotifySettings)
async def update_notify_settings(request: UpdateNotifySettings, user: User) -> bool:
    peer, not_peer = await PeerNotifySettings.peer_from_tl(user, request.peer)

    if request.settings.mute_until:
        muted_until = datetime.fromtimestamp(request.settings.mute_until, UTC)
    else:
        muted_until = None

    settings, _ = await PeerNotifySettings.update_or_create(user=user, peer=peer, not_peer=not_peer, defaults={
        "show_previews": request.settings.show_previews,
        "muted": request.settings.silent if request.settings.silent is not None else False,
        "muted_until": muted_until,
    })

    await upd.update_peer_notify_settings(user, peer, not_peer, settings)
    return True


# TODO: GetNotifyExceptions
# TODO: ResetNotifySettings
