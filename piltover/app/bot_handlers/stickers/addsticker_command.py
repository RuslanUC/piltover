from datetime import datetime, UTC

from piltover.app.bot_handlers.interaction_handler import BotInteractionHandler
from piltover.app.bot_handlers.stickers.utils import send_bot_message, get_stickerset_selection_keyboard
from piltover.db.enums import StickersBotState
from piltover.db.models import Peer, MessageRef
from piltover.db.models.stickers_state import StickersBotUserState
from piltover.tl import ReplyKeyboardMarkup

_text = "Choose a sticker set."
_text_no_sets = "You have no sets :("  # TODO: correct text


class AddSticker(BotInteractionHandler[StickersBotState, StickersBotUserState]):
    def __init__(self) -> None:
        super().__init__(StickersBotUserState)
        self.command("addsticker").do(self._handler).register()

    @staticmethod
    async def _handler(peer: Peer, _message: MessageRef, _state: None) -> MessageRef:
        keyboard_rows = await get_stickerset_selection_keyboard(peer.owner)
        if keyboard_rows is None:
            return await send_bot_message(peer, _text_no_sets)

        await StickersBotUserState.update_or_create(user=peer.owner, defaults={
            "state": StickersBotState.ADDSTICKER_WAIT_PACK,
            "data": None,
            "last_access": datetime.now(UTC),
        })

        return await send_bot_message(peer, _text, ReplyKeyboardMarkup(rows=keyboard_rows, single_use=True))
