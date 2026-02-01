from datetime import datetime, UTC

from piltover.app.bot_handlers.stickers.utils import send_bot_message
from piltover.db.enums import StickersBotState
from piltover.db.models import Peer, MessageRef
from piltover.db.models.stickers_state import StickersBotUserState

__text = "Yay! A new sticker set. Now choose a name for your set."


async def stickers_newpack_command(peer: Peer, _: MessageRef) -> MessageRef | None:
    await StickersBotUserState.update_or_create(user=peer.owner, defaults={
        "state": StickersBotState.NEWPACK_WAIT_NAME,
        "data": None,
        "last_access": datetime.now(UTC),
    })

    return await send_bot_message(peer, __text)
