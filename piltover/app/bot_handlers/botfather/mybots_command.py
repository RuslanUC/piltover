from piltover.app.bot_handlers.botfather.utils import get_bot_selection_inline_keyboard, send_bot_message
from piltover.app.bot_handlers.interaction_handler import BotInteractionHandler
from piltover.db.enums import BotFatherState
from piltover.db.models import Peer, MessageRef, BotFatherUserState
from piltover.tl import ReplyInlineMarkup

text_choose_bot = """
Choose a bot from the list below:
""".strip()
text_no_bots = """
You have currently no bots
""".strip()


class MyBots(BotInteractionHandler[BotFatherState, BotFatherUserState]):
    def __init__(self) -> None:
        super().__init__(BotFatherUserState)
        self.command("mybots").do(self._handler).register()

    @staticmethod
    async def _handler(peer: Peer, _message: MessageRef, _state: None) -> MessageRef:
        rows = await get_bot_selection_inline_keyboard(peer.owner, 0)
        if rows is None:
            return await send_bot_message(peer, text_no_bots)

        return await send_bot_message(peer, text_choose_bot, ReplyInlineMarkup(rows=rows))
