from datetime import datetime, UTC

from piltover.db.enums import StickersBotState
from piltover.db.models import Peer, Message
from piltover.db.models.stickers_state import StickersBotUserState

__text = """
Yay! A new sticker set. Now choose a name for your set.
"""


async def stickers_newpack_command(peer: Peer, _: Message) -> Message | None:
    await StickersBotUserState.update_or_create(user=peer.owner, defaults={
        "state": StickersBotState.NEWPACK_WAIT_NAME,
        "data": None,
        "last_access": datetime.now(UTC),
    })

    messages = await Message.create_for_peer(peer, None, None, peer.user, False, message=__text)
    return messages[peer]
