from time import time

from piltover.db.models.sentcode import SentCode
from piltover.db.models.user import User
from piltover.exceptions import ErrorRpc
from piltover.server import MessageHandler, Client
from piltover.tl.types import CoreMessage
from piltover.tl_new.functions.auth import SendCode, SignIn, BindTempAuthKey, ExportLoginToken, SignUp
from piltover.tl_new.types.auth import SentCode as TLSentCode, SentCodeTypeSms, Authorization, LoginToken, \
    AuthorizationSignUpRequired

handler = MessageHandler("auth")


# noinspection PyUnusedLocal
@handler.on_message(SendCode)
async def send_code(client: Client, request: CoreMessage[SendCode], session_id: int):
    try:
        int(request.obj.phone_number)
    except ValueError:
        raise ErrorRpc(error_code=406, error_message="PHONE_NUMBER_INVALID")

    code = await SentCode.create(phone_number=int(request.obj.phone_number))
    print(f"Code: {code.code}")

    return TLSentCode(
        type_=SentCodeTypeSms(length=5),
        phone_code_hash=code.phone_code_hash(),
        timeout=30,
    )


# noinspection PyUnusedLocal
@handler.on_message(SignIn)
async def sign_in(client: Client, request: CoreMessage[SignIn], session_id: int):
    if len(request.obj.phone_code_hash) != 24:
        raise ErrorRpc(error_code=400, error_message="PHONE_CODE_INVALID")
    if request.obj.phone_code is None:
        raise ErrorRpc(error_code=400, error_message="PHONE_CODE_EMPTY")
    try:
        int(request.obj.phone_code)
        int(request.obj.phone_number)
    except ValueError:
        raise ErrorRpc(error_code=406, error_message="PHONE_NUMBER_INVALID")
    code = await SentCode.get_or_none(phone_number=request.obj.phone_number, hash=request.obj.phone_code_hash[8:],
                                      used=False)
    if code is None or code.code != int(request.obj.phone_code):
        raise ErrorRpc(error_code=400, error_message="PHONE_CODE_INVALID")
    if code.expires_at < time():
        await code.delete()
        raise ErrorRpc(error_code=400, error_message="PHONE_CODE_EXPIRED")

    await code.update(used=True)

    if (user := await User.get_or_none(phone_number=request.obj.phone_number)) is None:
        return AuthorizationSignUpRequired()
        #raise ErrorRpc(error_code=400, error_message="PHONE_NUMBER_UNOCCUPIED") # ???

    return Authorization(user=user.to_tl_user(is_self=True))


# noinspection PyUnusedLocal
@handler.on_message(SignUp)
async def sign_up(client: Client, request: CoreMessage[SignUp], session_id: int):
    req = request.obj

    if len(req.phone_code_hash) != 24:
        raise ErrorRpc(error_code=400, error_message="PHONE_CODE_INVALID")
    try:
        int(req.phone_number)
    except ValueError:
        raise ErrorRpc(error_code=406, error_message="PHONE_NUMBER_INVALID")
    code = await SentCode.get_or_none(phone_number=req.phone_number, hash=req.phone_code_hash[8:],
                                      used=True)
    if code is None:
        raise ErrorRpc(error_code=400, error_message="PHONE_CODE_INVALID")
    if code.expires_at < time():
        await code.delete()
        raise ErrorRpc(error_code=400, error_message="PHONE_CODE_EXPIRED")

    if await User.filter(phone_number=req.phone_number).exists():
        raise ErrorRpc(error_code=400, error_message="PHONE_NUMBER_OCCUPIED")

    if not req.first_name or len(req.first_name) > 128:
        raise ErrorRpc(error_code=400, error_message="FIRSTNAME_INVALID")
    if req.last_name is not None and len(req.last_name) > 128:
        raise ErrorRpc(error_code=400, error_message="LASTNAME_INVALID")

    user = await User.create(phone_number=req.phone_number, first_name=req.first_name, last_name=req.last_name)
    return Authorization(user=user.to_tl_user(is_self=True))


# noinspection PyUnusedLocal
@handler.on_message(BindTempAuthKey)
async def bind_temp_auth_key(client: Client, request: CoreMessage[BindTempAuthKey], session_id: int):
    return True


# noinspection PyUnusedLocal
@handler.on_message(ExportLoginToken)
async def export_login_token(client: Client, request: CoreMessage[ExportLoginToken], session_id: int):
    return LoginToken(expires=1000, token=b"levlam")
