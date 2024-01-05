from time import time

from piltover.server import MessageHandler, Client
from piltover.tl.types import CoreMessage
from piltover.tl_new import StoriesStealthMode, Updates
from piltover.tl_new.functions.stories import GetAllStories, GetAllReadPeerStories
from piltover.tl_new.types.stories import AllStories

handler = MessageHandler("stories")


# noinspection PyUnusedLocal
@handler.on_message(GetAllStories)
async def get_all_stories(client: Client, request: CoreMessage[GetAllStories], session_id: int):
    return AllStories(
        has_more=False,
        count=0,
        state="",
        peer_stories=[],
        chats=[],
        users=[],
        stealth_mode=StoriesStealthMode(
            active_until_date=0,
            cooldown_until_date=0,
        ),
    )


@handler.on_message(GetAllReadPeerStories)
async def get_all_read_peer_stories(client: Client, request: CoreMessage[GetAllReadPeerStories], session_id: int):
    return Updates(updates=[], users=[], chats=[], date=int(time()), seq=0)
