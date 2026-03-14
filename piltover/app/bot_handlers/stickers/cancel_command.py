from typing import cast

from piltover.app.bot_handlers.interaction_handler import BotInteractionHandler
from piltover.app.bot_handlers.stickers.utils import send_bot_message
from piltover.app.utils.formatable_text_with_entities import FormatableTextWithEntities
from piltover.db.enums import StickersBotState, STICKERS_STATE_TO_COMMAND_NAME
from piltover.db.models import Peer, MessageRef
from piltover.db.models.stickers_state import StickersBotUserState

_text_no_command = """
No active command to cancel. I wasn't doing anything anyway. Zzzzz...
""".strip()
_text_command_cancel = FormatableTextWithEntities("""
The command {command} has been cancelled. Anything else I can do for you?

Send <c>/help</c> for a list of commands.
""".strip())


class Cancel(BotInteractionHandler[StickersBotState, StickersBotUserState]):
    def __init__(self) -> None:
        super().__init__(StickersBotUserState)
        self.command("cancel").do(self._handler).register()

    @staticmethod
    async def _handler(peer: Peer, _message: MessageRef, _state: None) -> MessageRef:
        state = cast(
            StickersBotState | None,
            await StickersBotUserState.filter(user=peer.owner).first().values_list("state", flat=True)
        )
        await StickersBotUserState.filter(user=peer.owner).delete()

        text = _text_no_command
        entities = []
        command = STICKERS_STATE_TO_COMMAND_NAME[state]

        if command is not None:
            text, entities = _text_command_cancel.format(command=command)

        return await send_bot_message(peer, text, entities=entities)
