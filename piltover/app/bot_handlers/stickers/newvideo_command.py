from datetime import datetime, UTC

from piltover.app.bot_handlers.interaction_handler import BotInteractionHandler
from piltover.app.bot_handlers.stickers.utils import send_bot_message
from piltover.app.utils.formatable_text_with_entities import FormatableTextWithEntities
from piltover.db.enums import StickersBotState
from piltover.db.models import Peer, MessageRef
from piltover.db.models.stickers_state import StickersBotUserState

_text, _entities = FormatableTextWithEntities("""
Yay! A new set of video stickers. If you're new to video stickers, please see these guidelines (<a>https://core.telegram.org/stickers#video-stickers</a>) before you proceed.

When ready to upload, tell me the name of your pack.
""".strip()).format()


class NewVideo(BotInteractionHandler[StickersBotState, StickersBotUserState]):
    def __init__(self) -> None:
        super().__init__(StickersBotUserState)
        self.command("newvideo").do(self._handler).register()

    @staticmethod
    async def _handler(peer: Peer, _message: MessageRef, _state: None) -> MessageRef:
        await StickersBotUserState.update_or_create(user=peer.owner, defaults={
            "state": StickersBotState.NEWVIDEO_WAIT_NAME,
            "data": None,
            "last_access": datetime.now(UTC),
        })

        return await send_bot_message(peer, _text, entities=_entities)
