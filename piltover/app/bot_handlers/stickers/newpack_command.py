from datetime import datetime, UTC

from piltover.app.bot_handlers.interaction_handler import BotInteractionHandler
from piltover.app.bot_handlers.stickers.utils import send_bot_message
from piltover.db.enums import StickersBotState
from piltover.db.models import Peer, MessageRef
from piltover.db.models.stickers_state import StickersBotUserState

_text = "Yay! A new sticker set. Now choose a name for your set."


class NewPack(BotInteractionHandler[StickersBotState, StickersBotUserState]):
    def __init__(self) -> None:
        super().__init__(StickersBotUserState)
        self.command("newpack").do(self._handler).register()

    @staticmethod
    async def _handler(peer: Peer, _message: MessageRef, _state: None) -> MessageRef:
        await StickersBotUserState.update_or_create(user=peer.owner, defaults={
            "state": StickersBotState.NEWPACK_WAIT_NAME,
            "data": None,
            "last_access": datetime.now(UTC),
        })

        return await send_bot_message(peer, _text)
