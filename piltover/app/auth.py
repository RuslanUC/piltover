from io import BytesIO
from time import time

from piltover.app.utils import check_password_internal
from piltover.db.models import AuthKey, UserAuthorization, UserPassword
from piltover.db.models.authkey import TempAuthKey
from piltover.db.models.sentcode import SentCode
from piltover.db.models.user import User
from piltover.enums import ReqHandlerFlags
from piltover.exceptions import ErrorRpc
from piltover.high_level import MessageHandler, Client
from piltover.tl.types import EncryptedMessage
from piltover.tl_new import Long, BindAuthKeyInner
from piltover.tl_new.functions.auth import SendCode, SignIn, BindTempAuthKey, ExportLoginToken, SignUp, CheckPassword
from piltover.tl_new.types.auth import SentCode as TLSentCode, SentCodeTypeSms, Authorization, LoginToken, \
    AuthorizationSignUpRequired

handler = MessageHandler("auth")


# noinspection PyUnusedLocal
@handler.on_request(SendCode)
async def send_code(client: Client, request: SendCode):
    try:
        int(request.phone_number)
    except ValueError:
        raise ErrorRpc(error_code=406, error_message="PHONE_NUMBER_INVALID")

    code = await SentCode.create(phone_number=int(request.phone_number))
    print(f"Code: {code.code}")

    return TLSentCode(
        type_=SentCodeTypeSms(length=5),
        phone_code_hash=code.phone_code_hash(),
        timeout=30,
    )


# noinspection PyUnusedLocal
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
    await UserAuthorization.create(ip="127.0.0.1", user=user, key=key, mfa_pending=password.password is not None)
    if password.password is not None:
        raise ErrorRpc(error_code=401, error_message="SESSION_PASSWORD_NEEDED")

    return Authorization(user=await user.to_tl(current_user=user))


# noinspection PyUnusedLocal
@handler.on_request(SignUp)
async def sign_up(client: Client, request: SignUp):
    if len(request.phone_code_hash) != 24:
        raise ErrorRpc(error_code=400, error_message="PHONE_CODE_INVALID")
    try:
        int(request.phone_number)
    except ValueError:
        raise ErrorRpc(error_code=406, error_message="PHONE_NUMBER_INVALID")
    code = await SentCode.get_or_none(phone_number=request.phone_number, hash=request.phone_code_hash[8:],
                                      used=True)
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


# noinspection PyUnusedLocal
@handler.on_request(CheckPassword, ReqHandlerFlags.AUTH_REQUIRED | ReqHandlerFlags.ALLOW_MFA_PENDING)
async def check_password(client: Client, request: CheckPassword, user: User):
    auth = await client.get_auth(True)
    if not auth.mfa_pending:  # ??
        return Authorization(user=await user.to_tl(current_user=user))

    password, _ = await UserPassword.get_or_create(user=user)
    await check_password_internal(password, request.password)

    await auth.update(mfa_pending=False)
    return Authorization(user=await user.to_tl(current_user=user))


# noinspection PyUnusedLocal
@handler.on_request(BindTempAuthKey)
async def bind_temp_auth_key(client: Client, request: BindTempAuthKey):
    data = BytesIO(request.encrypted_message)
    auth_key_id = Long.read(data)
    if auth_key_id != request.perm_auth_key_id:
        raise ErrorRpc(error_code=400, error_message="ENCRYPTED_MESSAGE_INVALID")
    msg_key = data.read(16)
    encrypted_data = data.read()
    try:
        message = await client.decrypt(EncryptedMessage(auth_key_id, msg_key, encrypted_data))
        # TODO: check message.message_id == request message id
        if message.seq_no != 0 or len(message.message_data) != 40:
            raise Exception

        obj = BindAuthKeyInner.read(BytesIO(message.message_data))
        # TODO: check obj.temp_session_id == request session id
        # TODO: check obj.temp_auth_key_id == request key id
        if obj.perm_auth_key_id != auth_key_id or obj.nonce != request.nonce:
            raise Exception
    except:
        raise ErrorRpc(error_code=400, error_message="ENCRYPTED_MESSAGE_INVALID")

    perm_key = await AuthKey.get(id=str(obj.perm_auth_key_id))
    await TempAuthKey.filter(perm_key__id=str(obj.perm_auth_key_id)).delete()
    await TempAuthKey.filter(id=str(obj.temp_auth_key_id)).update(perm_key=perm_key)

    return True


# noinspection PyUnusedLocal
@handler.on_request(ExportLoginToken)
async def export_login_token(client: Client, request: ExportLoginToken):
    return LoginToken(expires=1000, token=b"levlam")
