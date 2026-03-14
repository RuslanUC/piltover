from datetime import datetime, UTC

from piltover.app.bot_handlers.interaction_handler import BotInteractionHandler
from piltover.app.bot_handlers.stickers.utils import send_bot_message, EMOJI_PACK_TYPES_KEYBOARD
from piltover.db.enums import StickersBotState
from piltover.db.models import Peer, MessageRef
from piltover.db.models.stickers_state import StickersBotUserState

_text = """
Yay! A new set of custom emoji. We support 3 types of custom emoji: animated, video and static. Please choose the type:
""".strip()


class NewEmojiPack(BotInteractionHandler[StickersBotState, StickersBotUserState]):
    def __init__(self) -> None:
        super().__init__(StickersBotUserState)
        self.command("newemojipack").do(self._handler).register()

    @staticmethod
    async def _handler(peer: Peer, _message: MessageRef, _state: None) -> MessageRef:
        await StickersBotUserState.update_or_create(user=peer.owner, defaults={
            "state": StickersBotState.NEWEMOJIPACK_WAIT_TYPE,
            "data": None,
            "last_access": datetime.now(UTC),
        })

        return await send_bot_message(peer, _text, EMOJI_PACK_TYPES_KEYBOARD)
