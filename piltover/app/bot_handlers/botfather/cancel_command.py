from typing import cast

from piltover.app.bot_handlers.botfather.utils import send_bot_message
from piltover.app.bot_handlers.interaction_handler import BotInteractionHandler
from piltover.app.utils.formatable_text_with_entities import FormatableTextWithEntities
from piltover.db.enums import BotFatherState, BOTFATHER_STATE_TO_COMMAND_NAME
from piltover.db.models import Peer, BotFatherUserState, MessageRef

_text_no_command = """
No active command to cancel. I wasn't doing anything anyway. Zzzzz...
""".strip()
_text_command_cancel = FormatableTextWithEntities("""
The command {command} has been cancelled. Anything else I can do for you?

Send <c>/help</c> for a list of commands. To learn more about Telegram Bots, see <a>https://core.telegram.org/bots</a>
""".strip())


class Cancel(BotInteractionHandler[BotFatherState, BotFatherUserState]):
    def __init__(self) -> None:
        super().__init__(BotFatherUserState)
        self.command("cancel").do(self._handler).register()

    @staticmethod
    async def _handler(peer: Peer, _message: MessageRef, _state: None) -> MessageRef:
        state = cast(
            BotFatherState | None,
            await BotFatherUserState.filter(user=peer.owner).first().values_list("state", flat=True)
        )
        await BotFatherUserState.filter(user=peer.owner).delete()

        command = BOTFATHER_STATE_TO_COMMAND_NAME[state]
        if command is None:
            text, entities = _text_no_command, []
        else:
            text, entities = _text_command_cancel.format(command=command)

        return await send_bot_message(peer, text, entities=entities)
