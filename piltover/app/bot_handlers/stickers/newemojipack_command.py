from datetime import datetime, UTC

from piltover.app.bot_handlers.stickers.utils import send_bot_message, EMOJI_PACK_TYPES_KEYBOARD
from piltover.db.enums import StickersBotState
from piltover.db.models import Peer, MessageRef
from piltover.db.models.stickers_state import StickersBotUserState

__text = """
Yay! A new set of custom emoji. We support 3 types of custom emoji: animated, video and static. Please choose the type:
""".strip()


async def stickers_newemojipack_command(peer: Peer, _: MessageRef) -> MessageRef | None:
    await StickersBotUserState.update_or_create(user=peer.owner, defaults={
        "state": StickersBotState.NEWEMOJIPACK_WAIT_TYPE,
        "data": None,
        "last_access": datetime.now(UTC),
    })

    return await send_bot_message(peer, __text, EMOJI_PACK_TYPES_KEYBOARD)
