from time import time

from piltover.high_level import Client, MessageHandler
from piltover.tl_new.functions.updates import GetState
from piltover.tl_new.types.updates import State

handler = MessageHandler("auth")


# noinspection PyUnusedLocal
@handler.on_request(GetState)
async def get_state(client: Client, request: GetState):
    return State(
        pts=0,
        qts=0,
        seq=0,
        date=int(time()),
        unread_count=0,
    )
