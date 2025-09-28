from time import time

from piltover.enums import ReqHandlerFlags
from piltover.tl import StoriesStealthMode, Updates, IntVector
from piltover.tl.functions.stories import GetAllStories, GetAllReadPeerStories, GetPeerMaxIDs
from piltover.tl.types.stories import AllStories
from piltover.worker import MessageHandler

handler = MessageHandler("stories")


@handler.on_request(GetAllStories, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_all_stories():  # pragma: no cover
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


@handler.on_request(GetAllReadPeerStories, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_all_read_peer_stories():  # pragma: no cover
    return Updates(updates=[], users=[], chats=[], date=int(time()), seq=0)


@handler.on_request(GetPeerMaxIDs, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_peer_max_ids() -> list[int]:  # pragma: no cover
    return IntVector()
