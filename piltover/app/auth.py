from time import time

from piltover.db.models import AuthKey, UserAuthorization
from piltover.db.models.sentcode import SentCode
from piltover.db.models.user import User
from piltover.exceptions import ErrorRpc
from piltover.high_level import MessageHandler, Client
from piltover.tl_new.functions.auth import SendCode, SignIn, BindTempAuthKey, ExportLoginToken, SignUp
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

    key = await AuthKey.get(id=str(client.auth_data.auth_key_id))
    await UserAuthorization.create(ip="127.0.0.1", user=user, key=key)

    return Authorization(user=user.to_tl(current_user=user))


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
    key = await AuthKey.get(id=str(client.auth_data.auth_key_id))
    await UserAuthorization.create(ip="127.0.0.1", user=user, key=key)

    return Authorization(user=user.to_tl(current_user=user))


# noinspection PyUnusedLocal
@handler.on_request(BindTempAuthKey)
async def bind_temp_auth_key(client: Client, request: BindTempAuthKey):
    return True


# noinspection PyUnusedLocal
@handler.on_request(ExportLoginToken)
async def export_login_token(client: Client, request: ExportLoginToken):
    return LoginToken(expires=1000, token=b"levlam")
