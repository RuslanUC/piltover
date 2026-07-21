from datetime import datetime, UTC

from piltover.app.bot_handlers.botfather.utils import send_bot_message
from piltover.app.bot_handlers.interaction_handler import BotInteractionHandler
from piltover.config import APP_CONFIG
from piltover.db.enums import BotFatherState
from piltover.db.models import Peer, MessageRef, BotFatherUserState, Bot

_text = """
Alright, a new bot. How are we going to call it? Please choose a name for your bot.
""".strip()
_too_much_bots = """
You already have the maximum number of bots.
""".strip()


class NewBot(BotInteractionHandler[BotFatherState, BotFatherUserState]):
    def __init__(self) -> None:
        super().__init__(BotFatherUserState)
        self.command("newbot").do(self._handler).register()

    @staticmethod
    async def _handler(peer: Peer, _message: MessageRef, _state: None) -> MessageRef:
        if await Bot.filter(owner_id=peer.owner_id).count() >= APP_CONFIG.max_bots_per_user:
            return await send_bot_message(peer, _too_much_bots)

        await BotFatherUserState.update_or_create(user_id=peer.owner_id, defaults={
            "state": BotFatherState.NEWBOT_WAIT_NAME,
            "data": None,
            "last_access": datetime.now(UTC),
        })

        return await send_bot_message(peer, _text)

