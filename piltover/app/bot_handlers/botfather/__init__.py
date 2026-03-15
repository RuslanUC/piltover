from piltover.app.bot_handlers.botfather.cancel_command import Cancel
from piltover.app.bot_handlers.botfather.empty_command import Empty
from piltover.app.bot_handlers.botfather.mybots_command import MyBots
from piltover.app.bot_handlers.botfather.newbot_command import NewBot
from piltover.app.bot_handlers.botfather.text_handler import Text
from piltover.app.bot_handlers.interaction_handler import BotInteractionHandler
from piltover.app.bot_handlers.botfather.start_command import Start
from piltover.db.enums import BotFatherState
from piltover.db.models import BotFatherUserState


class BotfatherBotInteractionHandler(BotInteractionHandler[BotFatherState, BotFatherUserState]):
    def __init__(self) -> None:
        super().__init__(BotFatherUserState)

        self.include(Start())
        self.include(Cancel())
        self.include(Empty())
        self.include(MyBots())
        self.include(NewBot())
        self.include(Text())
