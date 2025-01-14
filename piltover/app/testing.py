from piltover.app.auth import send_code
from piltover.db.models.sentcode import SentCode
from piltover.enums import ReqHandlerFlags
from piltover.worker import MessageHandler
from piltover.tl.functions.auth import SendCode
from piltover.tl.types.auth import SentCode as TLSentCode

handler = MessageHandler("testing")


@handler.on_request(SendCode, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def send_code_test(request: SendCode):
    result = await send_code(request)
    if isinstance(result, TLSentCode):
        await SentCode.filter(phone_number=int(request.phone_number)).update(code=22222)

    return result