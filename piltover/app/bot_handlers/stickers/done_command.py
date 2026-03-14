from piltover.app.bot_handlers.interaction_handler import BotInteractionHandler
from piltover.app.bot_handlers.stickers.utils import send_bot_message
from piltover.db.enums import StickersBotState
from piltover.db.models import StickersBotUserState

_text = "OK, well done!"
_text_no_done = "This command was a bit out of place here. Are you sure you meant that?"


class Done(BotInteractionHandler[StickersBotState, StickersBotUserState]):
    def __init__(self) -> None:
        super().__init__(StickersBotUserState)

        (
            self.command("done").set_send_message_func(send_bot_message)

            .when(state=StickersBotState.ADDSTICKER_WAIT_IMAGE).delete_state().respond(_text).ok()
            .when(state=StickersBotState.ADDSTICKER_WAIT_EMOJI).delete_state().respond(_text).ok()
            .when(state=StickersBotState.ADDEMOJI_WAIT_IMAGE).delete_state().respond(_text).ok()
            .when(state=StickersBotState.ADDEMOJI_WAIT_EMOJI).delete_state().respond(_text).ok()
            .otherwise().respond(_text_no_done).ok()

            .register()
        )
