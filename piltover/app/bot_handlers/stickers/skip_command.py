from piltover.app.bot_handlers.interaction_handler import BotInteractionHandler
from piltover.app.bot_handlers.stickers.utils import send_bot_message
from piltover.app.utils.formatable_text_with_entities import FormatableTextWithEntities
from piltover.db.enums import StickersBotState
from piltover.db.models import StickersBotUserState

_text_no_skip = "Sorry, this step can't be skipped"
_text_icon_skipped, _text_icon_skipped_entities = FormatableTextWithEntities("""
Please provide a short name for your set. I'll use it to create a link that you can share with friends and followers.

For example, this set has the short name 'Animals': <a>https://telegram.me/addstickers/Animals</a>
""".strip()).format()
_text_icon_skipped_emoji, _text_icon_skipped_emoji_entities = FormatableTextWithEntities("""
Please provide a short name for your emoji set. I'll use it to create a link that you can share with friends and followers.

For example, this set has the short name 'DuckEmoji': <a>https://telegram.me/addemoji/DuckEmoji</a>
""".strip()).format()


class Skip(BotInteractionHandler[StickersBotState, StickersBotUserState]):
    def __init__(self) -> None:
        super().__init__(StickersBotUserState)

        (
            self.command("skip").set_send_message_func(send_bot_message)

            .when(state=StickersBotState.NEWPACK_WAIT_ICON)
            .set_state(StickersBotState.NEWPACK_WAIT_SHORT_NAME)
            .respond(_text_icon_skipped, _text_icon_skipped_entities).ok()

            .when(state=StickersBotState.NEWEMOJIPACK_WAIT_ICON)
            .set_state(StickersBotState.NEWEMOJIPACK_WAIT_SHORT_NAME)
            .respond(_text_icon_skipped_emoji, _text_icon_skipped_emoji_entities).ok()

            .when(state=StickersBotState.NEWVIDEO_WAIT_ICON)
            .set_state(StickersBotState.NEWVIDEO_WAIT_SHORT_NAME)
            .respond(_text_icon_skipped, _text_icon_skipped_entities).ok()

            .otherwise().respond(_text_no_skip).ok()

            .register()
        )
