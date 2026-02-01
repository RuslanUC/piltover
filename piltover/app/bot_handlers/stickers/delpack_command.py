from datetime import datetime, UTC

from piltover.app.bot_handlers.stickers.utils import send_bot_message, get_stickerset_selection_keyboard
from piltover.db.enums import StickersBotState
from piltover.db.models import Peer, MessageRef
from piltover.db.models.stickers_state import StickersBotUserState
from piltover.tl import ReplyKeyboardMarkup

__text = "Choose the sticker set you want to delete."
__text_no_sets = "You have no sets :("  # TODO: correct text


async def stickers_delpack_command(peer: Peer, _: MessageRef) -> MessageRef | None:
    keyboard_rows = await get_stickerset_selection_keyboard(peer.owner, None)
    if keyboard_rows is None:
        return await send_bot_message(peer, __text_no_sets)

    await StickersBotUserState.update_or_create(user=peer.owner, defaults={
        "state": StickersBotState.DELPACK_WAIT_PACK,
        "data": None,
        "last_access": datetime.now(UTC),
    })

    return await send_bot_message(peer, __text, ReplyKeyboardMarkup(rows=keyboard_rows, single_use=True))
