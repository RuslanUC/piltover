from time import time

from piltover.high_level import MessageHandler, Client
from piltover.tl_new import StoriesStealthMode, Updates
from piltover.tl_new.functions.stories import GetAllStories, GetAllReadPeerStories
from piltover.tl_new.types.stories import AllStories

handler = MessageHandler("stories")


# noinspection PyUnusedLocal
@handler.on_request(GetAllStories)
async def get_all_stories(client: Client, request: GetAllStories):
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


# noinspection PyUnusedLocal
@handler.on_request(GetAllReadPeerStories)
async def get_all_read_peer_stories(client: Client, request: GetAllReadPeerStories):
    return Updates(updates=[], users=[], chats=[], date=int(time()), seq=0)
