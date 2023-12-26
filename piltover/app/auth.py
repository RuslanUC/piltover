from piltover.app import user
from piltover.server import MessageHandler, Client
from piltover.tl.types import CoreMessage
from piltover.tl_new.functions.auth import SendCode, SignIn, BindTempAuthKey, ExportLoginToken
from piltover.tl_new.types.auth import SentCode, SentCodeTypeSms, Authorization, LoginToken

handler = MessageHandler("auth")


# noinspection PyUnusedLocal
@handler.on_message(SendCode)
async def send_code(client: Client, request: CoreMessage[SendCode], session_id: int):
    from binascii import crc32

    code = 69696
    code = str(code).encode()

    return SentCode(
        type_=SentCodeTypeSms(length=len(code)),
        phone_code_hash=f"{crc32(code):x}".zfill(8),
        timeout=30,
    )


# noinspection PyUnusedLocal
@handler.on_message(SignIn)
async def sign_in(client: Client, request: CoreMessage[SignIn], session_id: int):
    return Authorization(user=user)


# noinspection PyUnusedLocal
@handler.on_message(BindTempAuthKey)
async def bind_temp_auth_key(client: Client, request: CoreMessage[BindTempAuthKey], session_id: int):
    return True


# noinspection PyUnusedLocal
@handler.on_message(ExportLoginToken)
async def export_login_token(client: Client, request: CoreMessage[ExportLoginToken], session_id: int):
    return LoginToken(expires=1000, token=b"levlam")
