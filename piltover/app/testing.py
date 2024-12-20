from piltover.app.auth import send_code
from piltover.db.models.sentcode import SentCode
from piltover.high_level import MessageHandler, Client
from piltover.tl.functions.auth import SendCode
from piltover.tl.types.auth import SentCode as TLSentCode

handler = MessageHandler("testing")


# noinspection PyUnusedLocal
@handler.on_request(SendCode)
async def send_code_test(client: Client, request: SendCode):
    result = await send_code(client, request)
    if isinstance(result, TLSentCode):
        await SentCode.filter(phone_number=int(request.phone_number)).update(code=22222)

    return result