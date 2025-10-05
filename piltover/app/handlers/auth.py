from datetime import timedelta, datetime
from io import BytesIO
from typing import cast
from uuid import uuid4

from loguru import logger
from mtproto import ConnectionRole
from mtproto.packets import EncryptedMessagePacket, MessagePacket
from pytz import UTC
from tortoise.expressions import Q

import piltover.app.utils.updates_manager as upd
from piltover.app.utils.utils import check_password_internal
from piltover.app_config import AppConfig
from piltover.context import request_ctx
from piltover.db.enums import PeerType
from piltover.db.models import AuthKey, UserAuthorization, UserPassword, Peer, Dialog, Message, TempAuthKey, SentCode, \
    User, QrLogin, PhoneCodePurpose
from piltover.enums import ReqHandlerFlags
from piltover.exceptions import ErrorRpc
from piltover.session_manager import SessionManager
from piltover.tl import BindAuthKeyInner, UpdatesTooLong, Authorization, UpdateLoginToken
from piltover.tl.functions.auth import SendCode, SignIn, BindTempAuthKey, ExportLoginToken, SignUp, CheckPassword, \
    SignUp_133, LogOut, ResetAuthorizations, AcceptLoginToken, ResendCode, CancelCode
from piltover.tl.types.auth import SentCode as TLSentCode, SentCodeTypeSms, Authorization as AuthAuthorization, \
    LoginToken, AuthorizationSignUpRequired, SentCodeTypeApp, LoggedOut, LoginTokenSuccess
from piltover.utils.snowflake import Snowflake
from piltover.utils.utils import sec_check
from piltover.worker import MessageHandler

handler = MessageHandler("auth")

LOGIN_MESSAGE_FMT = (
    f"Login code: {{code}}. Do not give this code to anyone, even if they say they are from {AppConfig.NAME}!\n\n"
    f"❗️This code can be used to log in to your {AppConfig.NAME} account. We never ask it for anything else.\n\n"
    "If you didn't request this code by trying to log in on another device, simply ignore this message."
)


def _validate_phone(phone_number: str) -> None:
    try:
        if int(phone_number) < 100000:
            raise ValueError
    except ValueError:
        raise ErrorRpc(error_code=406, error_message="PHONE_NUMBER_INVALID")


async def _send_or_resend_code(phone_number: str, code_hash: str | None) -> TLSentCode:
    _validate_phone(phone_number)

    if code_hash is None:
        code = await SentCode.create(phone_number=phone_number, purpose=PhoneCodePurpose.SIGNIN)
    else:
        if len(code_hash) != SentCode.CODE_HASH_SIZE:
            raise ErrorRpc(error_code=400, error_message="PHONE_CODE_EMPTY")

        code = await SentCode.get_(phone_number, code_hash, None)
        await SentCode.check_raise_cls(code, None)

        code.code = SentCode.gen_phone_code()
        code.hash = uuid4()
        code.expires_at = SentCode.gen_expires_at()
        await code.save(update_fields=["code", "hash", "expires_at"])

    print(f"Code: {code.code}")

    resp = TLSentCode(
        type_=SentCodeTypeSms(length=5),
        phone_code_hash=code.phone_code_hash(),
        timeout=30,
    )

    user = await User.get_or_none(phone_number=phone_number)
    if user is None:
        return resp

    system_user = await User.get_or_none(id=777000)
    if system_user is None:
        return resp

    peer_system, _ = await Peer.get_or_create(owner=user, user=system_user, type=PeerType.USER)
    await Dialog.get_or_create(peer=peer_system)
    message = await Message.create(
        internal_id=Snowflake.make_id(),
        message=LOGIN_MESSAGE_FMT.format(code=str(code.code).zfill(5)),
        author=system_user,
        peer=peer_system,
    )

    await upd.send_message(user, {peer_system: message}, False)

    resp.type_ = SentCodeTypeApp(length=5)
    return resp


@handler.on_request(SendCode, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def send_code(request: SendCode):
    return await _send_or_resend_code(request.phone_number, None)


@handler.on_request(SignIn, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def sign_in(request: SignIn):
    if len(request.phone_code_hash) != SentCode.CODE_HASH_SIZE:
        raise ErrorRpc(error_code=400, error_message="PHONE_CODE_INVALID")
    if request.phone_code is None:
        raise ErrorRpc(error_code=400, error_message="PHONE_CODE_EMPTY")
    _validate_phone(request.phone_number)
    try:
        int(request.phone_code)
    except ValueError:
        raise ErrorRpc(error_code=406, error_message="PHONE_CODE_INVALID")

    code = await SentCode.get_(request.phone_number, request.phone_code_hash, PhoneCodePurpose.SIGNIN)
    await SentCode.check_raise_cls(code, request.phone_code)

    code.used = False
    code.expires_at = SentCode.gen_expires_at()
    code.purpose = PhoneCodePurpose.SIGNUP
    await code.save(update_fields=["used", "expires_at", "purpose"])

    if (user := await User.get_or_none(phone_number=request.phone_number)) is None:
        return AuthorizationSignUpRequired()

    password, _ = await UserPassword.get_or_create(user=user)

    key = await AuthKey.get(id=request_ctx.get().perm_auth_key_id)
    await UserAuthorization.filter(key=key).delete()
    auth = await UserAuthorization.create(ip="127.0.0.1", user=user, key=key, mfa_pending=password.password is not None)
    if password.password is not None:
        raise ErrorRpc(error_code=401, error_message="SESSION_PASSWORD_NEEDED")

    if not auth.mfa_pending:
        await upd.new_auth(user, auth)

    return AuthAuthorization(user=await user.to_tl(current_user=user))


@handler.on_request(SignUp_133, ReqHandlerFlags.AUTH_NOT_REQUIRED)
@handler.on_request(SignUp, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def sign_up(request: SignUp | SignUp_133):
    if len(request.phone_code_hash) != SentCode.CODE_HASH_SIZE:
        raise ErrorRpc(error_code=400, error_message="PHONE_CODE_INVALID")
    _validate_phone(request.phone_number)

    code = await SentCode.get_(request.phone_number, request.phone_code_hash, PhoneCodePurpose.SIGNUP)
    await SentCode.check_raise_cls(code, None)

    code.used = True
    await code.save(update_fields=["used"])

    if await User.filter(phone_number=request.phone_number).exists():
        raise ErrorRpc(error_code=400, error_message="PHONE_NUMBER_OCCUPIED")

    if not request.first_name or len(request.first_name) > 128:
        raise ErrorRpc(error_code=400, error_message="FIRSTNAME_INVALID")
    if request.last_name is not None and len(request.last_name) > 128:
        raise ErrorRpc(error_code=400, error_message="LASTNAME_INVALID")

    user = await User.create(
        phone_number=request.phone_number,
        first_name=request.first_name,
        last_name=request.last_name
    )
    key = await AuthKey.get(id=request_ctx.get().perm_auth_key_id)
    await UserAuthorization.create(ip="127.0.0.1", user=user, key=key)

    # TODO: send notification to all users that have new user's number as contact if no_joined_notifications is False

    return AuthAuthorization(user=await user.to_tl(current_user=user))


@handler.on_request(CheckPassword, ReqHandlerFlags.ALLOW_MFA_PENDING)
async def check_password(request: CheckPassword, user: User):
    ctx = request_ctx.get()
    auth = await UserAuthorization.get_or_none(id=ctx.auth_id, user__id=ctx.user_id)
    if not auth.mfa_pending:  # ??
        return AuthAuthorization(user=await user.to_tl(current_user=user))

    password, _ = await UserPassword.get_or_create(user=user)
    await check_password_internal(password, request.password)

    auth.mfa_pending = False
    await auth.save(update_fields=["mfa_pending"])

    await upd.new_auth(user, auth)

    return AuthAuthorization(user=await user.to_tl(current_user=user))


@handler.on_request(BindTempAuthKey, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def bind_temp_auth_key(request: BindTempAuthKey):
    ctx = request_ctx.get()

    encrypted_message = MessagePacket.parse(request.encrypted_message)
    if not isinstance(encrypted_message, EncryptedMessagePacket):
        raise ErrorRpc(error_code=400, error_message="ENCRYPTED_MESSAGE_INVALID")

    encrypted_message = cast(EncryptedMessagePacket, encrypted_message)

    if encrypted_message.auth_key_id != request.perm_auth_key_id:
        logger.debug(f"Perm auth key id mismatch: {encrypted_message.auth_key_id} != {request.perm_auth_key_id}")
        raise ErrorRpc(error_code=400, error_message="ENCRYPTED_MESSAGE_INVALID")

    perm_key = await AuthKey.get_or_none(id=str(encrypted_message.auth_key_id))

    try:
        sec_check(perm_key is not None)

        message = encrypted_message.decrypt(perm_key.auth_key, ConnectionRole.CLIENT, True)
        sec_check(message.seq_no == 0)
        sec_check(len(message.data) == 40)
        sec_check(message.message_id == ctx.message_id)

        obj = BindAuthKeyInner.read(BytesIO(message.data))
        sec_check(obj.perm_auth_key_id == encrypted_message.auth_key_id)
        sec_check(obj.nonce == request.nonce)
        sec_check(obj.temp_session_id == ctx.session_id)
        sec_check(obj.temp_auth_key_id == ctx.auth_key_id)
    except Exception as e:
        logger.opt(exception=e).debug("Failed to decrypt inner message")
        raise ErrorRpc(error_code=400, error_message="ENCRYPTED_MESSAGE_INVALID")

    await TempAuthKey.filter(perm_key=perm_key, id__not=str(obj.temp_auth_key_id)).delete()
    await TempAuthKey.filter(id=str(obj.temp_auth_key_id)).update(perm_key=perm_key)

    return True


@handler.on_request(ExportLoginToken, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def export_login_token():  # TODO: test
    ctx = request_ctx.get()
    if ctx.auth_id:
        auth = await UserAuthorization.get_or_none(id=ctx.auth_id).select_related("user")
        return LoginTokenSuccess(authorization=AuthAuthorization(user=await auth.user.to_tl(current_user=auth.user)))

    key = await AuthKey.get_or_temp(ctx.auth_key_id)
    if isinstance(key, TempAuthKey):
        key = key.perm_key

    login_q = Q(key=key) & (
        Q(created_at__gt=datetime.now(UTC) - timedelta(seconds=QrLogin.EXPIRE_TIME))
        | Q(auth__not=None)
    )

    login = await QrLogin.get_or_none(login_q).select_related("auth", "auth__user")
    if login is None:
        login = await QrLogin.create(key=key)

    if login.auth is not None:
        if login.auth.mfa_pending:
            raise ErrorRpc(error_code=401, error_message="SESSION_PASSWORD_NEEDED")
        user = login.auth.user
        return LoginTokenSuccess(authorization=AuthAuthorization(user=await user.to_tl(current_user=user)))

    return LoginToken(expires=int(login.created_at.timestamp()) + QrLogin.EXPIRE_TIME, token=login.to_token())


@handler.on_request(AcceptLoginToken)
async def accept_login_token(request: AcceptLoginToken, user: User) -> Authorization:  # TODO: test
    login = await QrLogin.from_token(request.token)
    if login is None:
        raise ErrorRpc(error_code=400, error_message="AUTH_TOKEN_INVALID")
    if login.auth_id is not None:
        raise ErrorRpc(error_code=400, error_message="AUTH_TOKEN_ALREADY_ACCEPTED")
    if (login.created_at + timedelta(seconds=QrLogin.EXPIRE_TIME)) < datetime.now(UTC):
        raise ErrorRpc(error_code=400, error_message="AUTH_TOKEN_EXPIRED")

    password, _ = await UserPassword.get_or_create(user=user)
    auth = await UserAuthorization.create(
        ip="127.0.0.1", user=user, key=login.key, mfa_pending=password.password is not None,
    )

    key_ids = await login.key.get_ids()
    await SessionManager.send(UpdateLoginToken(), key_id=key_ids)

    return auth.to_tl()


@handler.on_request(LogOut)
async def log_out() -> LoggedOut:
    await UserAuthorization.filter(key__id=request_ctx.get().perm_auth_key_id).delete()
    return LoggedOut()


@handler.on_request(ResetAuthorizations)
async def reset_authorizations(user: User) -> bool:
    auth_id = request_ctx.get().auth_id
    this_auth = await UserAuthorization.get_or_none(id=auth_id)

    if (this_auth.created_at + timedelta(days=1)) > datetime.now(UTC):
        raise ErrorRpc(error_code=406, error_message="FRESH_RESET_AUTHORISATION_FORBIDDEN")

    auths = await UserAuthorization.filter(user=user, id__not=auth_id).select_related("key")

    keys = [auth.key.id for auth in auths]
    temp_keys_ids = await TempAuthKey.filter(perm_key__id__in=keys).values_list("id", flat=True)
    keys.extend(temp_keys_ids)

    await UserAuthorization.filter(id__in=[auth.id for auth in auths]).delete()

    await SessionManager.send(UpdatesTooLong(), key_id=keys)

    return True


@handler.on_request(ResendCode, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def resend_code(request: ResendCode) -> TLSentCode:
    return await _send_or_resend_code(request.phone_number, request.phone_code_hash)


@handler.on_request(CancelCode, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def cancel_code(request: CancelCode) -> bool:
    _validate_phone(request.phone_number)
    if len(request.phone_code_hash) != SentCode.CODE_HASH_SIZE:
        raise ErrorRpc(error_code=400, error_message="PHONE_CODE_INVALID")

    code = await SentCode.get_(request.phone_number, request.phone_code_hash, None)
    await SentCode.check_raise_cls(code, None)
    await code.delete()

    return True
