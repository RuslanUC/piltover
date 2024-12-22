from io import BytesIO
from time import time
from typing import cast

from loguru import logger
from mtproto.packets import EncryptedMessagePacket, MessagePacket

from piltover.app.utils.updates_manager import UpdatesManager
from piltover.app.utils.utils import check_password_internal
from piltover.context import request_ctx
from piltover.db.enums import PeerType
from piltover.db.models import AuthKey, UserAuthorization, UserPassword, Peer, Dialog, Message
from piltover.db.models.authkey import TempAuthKey
from piltover.db.models.sentcode import SentCode
from piltover.db.models.user import User
from piltover.enums import ReqHandlerFlags
from piltover.exceptions import ErrorRpc
from piltover.high_level import MessageHandler, Client
from piltover.tl import BindAuthKeyInner
from piltover.tl.functions.auth import SendCode, SignIn, BindTempAuthKey, ExportLoginToken, SignUp, CheckPassword, \
    SignUp_136, LogOut
from piltover.tl.types.auth import SentCode as TLSentCode, SentCodeTypeSms, Authorization, LoginToken, \
    AuthorizationSignUpRequired, SentCodeTypeApp, LoggedOut
from piltover.utils.snowflake import Snowflake
from piltover.utils.utils import sec_check

handler = MessageHandler("auth")

LOGIN_MESSAGE_FMT = (
    "Login code: {code}. Do not give this code to anyone, even if they say they are from Piltover!\n\n"
    "❗️This code can be used to log in to your Piltover account. We never ask it for anything else.\n\n"
    "If you didn't request this code by trying to log in on another device, simply ignore this message."
)


@handler.on_request(SendCode)
async def send_code(request: SendCode):
    try:
        if int(request.phone_number) < 100000:
            raise ValueError
    except ValueError:
        raise ErrorRpc(error_code=406, error_message="PHONE_NUMBER_INVALID")

    code = await SentCode.create(phone_number=int(request.phone_number))
    print(f"Code: {code.code}")

    resp = TLSentCode(
        type_=SentCodeTypeSms(length=5),
        phone_code_hash=code.phone_code_hash(),
        timeout=30,
    )

    user = await User.get_or_none(phone_number=request.phone_number)
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

    await UpdatesManager.send_message(user, {peer_system: message})

    resp.type_ = SentCodeTypeApp(length=5)
    return resp


@handler.on_request(SignIn)
async def sign_in(client: Client, request: SignIn):
    if len(request.phone_code_hash) != 24:
        raise ErrorRpc(error_code=400, error_message="PHONE_CODE_INVALID")
    if request.phone_code is None:
        raise ErrorRpc(error_code=400, error_message="PHONE_CODE_EMPTY")
    try:
        int(request.phone_number)
    except ValueError:
        raise ErrorRpc(error_code=406, error_message="PHONE_NUMBER_INVALID")
    try:
        int(request.phone_code)
    except ValueError:
        raise ErrorRpc(error_code=406, error_message="PHONE_CODE_INVALID")
    code = await SentCode.get_or_none(phone_number=request.phone_number, hash=request.phone_code_hash[8:],
                                      used=False)
    if code is None or code.code != int(request.phone_code):
        raise ErrorRpc(error_code=400, error_message="PHONE_CODE_INVALID")
    if code.expires_at < time():
        await code.delete()
        raise ErrorRpc(error_code=400, error_message="PHONE_CODE_EXPIRED")

    await code.update(used=True)

    if (user := await User.get_or_none(phone_number=request.phone_number)) is None:
        return AuthorizationSignUpRequired()

    password, _ = await UserPassword.get_or_create(user=user)

    key = await AuthKey.get_or_temp(client.auth_data.auth_key_id)
    if isinstance(key, TempAuthKey):
        key = key.perm_key
    await UserAuthorization.filter(key=key).delete()
    await UserAuthorization.create(ip="127.0.0.1", user=user, key=key, mfa_pending=password.password is not None)
    if password.password is not None:
        raise ErrorRpc(error_code=401, error_message="SESSION_PASSWORD_NEEDED")

    return Authorization(user=await user.to_tl(current_user=user))


@handler.on_request(SignUp_136)
@handler.on_request(SignUp)
async def sign_up(client: Client, request: SignUp | SignUp_136):
    if len(request.phone_code_hash) != 24:
        raise ErrorRpc(error_code=400, error_message="PHONE_CODE_INVALID")
    try:
        int(request.phone_number)
    except ValueError:
        raise ErrorRpc(error_code=406, error_message="PHONE_NUMBER_INVALID")
    code = await SentCode.get_or_none(phone_number=request.phone_number, hash=request.phone_code_hash[8:], used=True)
    if code is None:
        raise ErrorRpc(error_code=400, error_message="PHONE_CODE_INVALID")
    if code.expires_at < time():
        await code.delete()
        raise ErrorRpc(error_code=400, error_message="PHONE_CODE_EXPIRED")

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
    key = await AuthKey.get_or_temp(client.auth_data.auth_key_id)
    if isinstance(key, TempAuthKey):
        key = key.perm_key
    await UserAuthorization.create(ip="127.0.0.1", user=user, key=key)

    return Authorization(user=await user.to_tl(current_user=user))


@handler.on_request(CheckPassword, ReqHandlerFlags.AUTH_REQUIRED | ReqHandlerFlags.ALLOW_MFA_PENDING)
async def check_password(client: Client, request: CheckPassword, user: User):
    auth = await client.get_auth(True)
    if not auth.mfa_pending:  # ??
        return Authorization(user=await user.to_tl(current_user=user))

    password, _ = await UserPassword.get_or_create(user=user)
    await check_password_internal(password, request.password)

    await auth.update(mfa_pending=False)
    return Authorization(user=await user.to_tl(current_user=user))


@handler.on_request(BindTempAuthKey)
async def bind_temp_auth_key(client: Client, request: BindTempAuthKey):
    ctx = request_ctx.get()

    encrypted_message = MessagePacket.parse(request.encrypted_message)
    if not isinstance(encrypted_message, EncryptedMessagePacket):
        raise ErrorRpc(error_code=400, error_message="ENCRYPTED_MESSAGE_INVALID")

    encrypted_message = cast(EncryptedMessagePacket, encrypted_message)

    if encrypted_message.auth_key_id != request.perm_auth_key_id:
        logger.debug(f"Perm auth key id mismatch: {encrypted_message.auth_key_id} != {request.perm_auth_key_id}")
        raise ErrorRpc(error_code=400, error_message="ENCRYPTED_MESSAGE_INVALID")

    try:
        message = await client.decrypt_noreplace(encrypted_message, True)
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

    perm_key = await AuthKey.get(id=str(obj.perm_auth_key_id))
    await TempAuthKey.filter(perm_key=perm_key, id__not=str(obj.temp_auth_key_id)).delete()
    await TempAuthKey.filter(id=str(obj.temp_auth_key_id)).update(perm_key=perm_key)

    return True


@handler.on_request(ExportLoginToken)
async def export_login_token():
    return LoginToken(expires=1000, token=b"levlam")


@handler.on_request(LogOut, ReqHandlerFlags.AUTH_REQUIRED)
async def log_out(client: Client) -> LoggedOut:
    key = await AuthKey.get_or_temp(client.auth_data.auth_key_id)
    if isinstance(key, TempAuthKey):
        key = key.perm_key
    await UserAuthorization.filter(key=key).delete()

    return LoggedOut()
