from time import time

from piltover.server import Client, MessageHandler
from piltover.tl.types import CoreMessage
from piltover.tl_new.functions.updates import GetState
from piltover.tl_new.types.updates import State

handler = MessageHandler("auth")


# noinspection PyUnusedLocal
@handler.on_message(GetState)
async def get_state(client: Client, request: CoreMessage[GetState], session_id: int):
    return State(
        pts=0,
        qts=0,
        seq=0,
        date=int(time()),
        unread_count=0,
    )
