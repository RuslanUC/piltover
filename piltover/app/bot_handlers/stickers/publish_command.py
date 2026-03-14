from io import BytesIO

from piltover.app.bot_handlers.interaction_handler import BotInteractionHandler
from piltover.app.bot_handlers.stickers.utils import send_bot_message
from piltover.app.utils.formatable_text_with_entities import FormatableTextWithEntities
from piltover.db.enums import StickersBotState
from piltover.db.models import Peer, StickersBotUserState, MessageRef
from piltover.tl.types.internal_stickersbot import StickersStateNewpack, StickersStateNewemojipack

_text_no_publish, _text_no_publish_entities = FormatableTextWithEntities(
    "You don't have any sticker sets yet. Use the <c>/newpack</c> command to create a new set first."
).format()
_text_set_icon, _text_set_icon_entities = FormatableTextWithEntities("""
You can set an icon for your sticker set. Telegram apps will display it in the list of stickers in the sticker panel.

To set an icon, send me a square 100x100 image in PNG or WEBP format with a transparent layer.

You can <c>/skip</c> this step. If you do, apps will use the first sticker of your pack as its icon.
""".strip()).format()
_text_set_icon_emoji, _text_set_icon_emoji_entities = FormatableTextWithEntities("""
You can send me a custom emoji from your emoji set to use it as an icon. Telegram apps will display it in the list of emoji in the emoji panel.

You can also <c>/skip</c> this step. If you do, apps will use the first emoji of your pack as its icon.
""".strip()).format()
_text_video_set_icon, _text_video_set_icon_entities = FormatableTextWithEntities("""
You can set an icon for your video sticker set. Telegram apps will display it in the list of stickers in the sticker panel.

To set an icon, send me a WEBM file up to **32 KB**. The dimensions of the icon must be **100x100 px**. The animation must be looped, and take no more than **3 seconds**.

You can <c>/skip</c> this step. If you do, apps will use the first sticker of your pack as its icon.
""".strip()).format()


class Publish(BotInteractionHandler[StickersBotState, StickersBotUserState]):
    def __init__(self) -> None:
        super().__init__(StickersBotUserState)

        (
            self.command("publish").set_send_message_func(send_bot_message)

            .when(state=StickersBotState.NEWPACK_WAIT_ICON).do(self._handle_newpack)
            .when(state=StickersBotState.NEWPACK_WAIT_EMOJI).do(self._handle_newpack)

            .when(state=StickersBotState.NEWEMOJIPACK_WAIT_IMAGE).do(self._handle_newemojipack)
            .when(state=StickersBotState.NEWEMOJIPACK_WAIT_EMOJI).do(self._handle_newemojipack)

            .when(state=StickersBotState.NEWVIDEO_WAIT_VIDEO).do(self._handle_newvideo)
            .when(state=StickersBotState.NEWVIDEO_WAIT_EMOJI).do(self._handle_newvideo)

            .otherwise().respond(_text_no_publish, _text_no_publish_entities).ok()

            .register()
        )

    @staticmethod
    async def _handle_newpack(peer: Peer, _: MessageRef, state: StickersBotUserState) -> MessageRef | None:
        state_data = StickersStateNewpack.deserialize(BytesIO(state.data))
        if not state_data.stickers or (len(state_data.stickers) == 1 and not state_data.stickers[0].emoji):
            return await send_bot_message(peer, _text_no_publish, entities=_text_no_publish_entities)

        await state.update_state(StickersBotState.NEWPACK_WAIT_ICON, None)
        return await send_bot_message(peer, _text_set_icon, entities=_text_set_icon_entities)

    @staticmethod
    async def _handle_newemojipack(peer: Peer, _: MessageRef, state: StickersBotUserState) -> MessageRef | None:
        state_data = StickersStateNewemojipack.deserialize(BytesIO(state.data))
        if not state_data.stickers or (len(state_data.stickers) == 1 and not state_data.stickers[0].emoji):
            return await send_bot_message(peer, _text_no_publish, entities=_text_no_publish_entities)

        await state.update_state(StickersBotState.NEWEMOJIPACK_WAIT_ICON, None)
        return await send_bot_message(peer, _text_set_icon_emoji, entities=_text_set_icon_emoji_entities)

    @staticmethod
    async def _handle_newvideo(peer: Peer, _: MessageRef, state: StickersBotUserState) -> MessageRef | None:
        state_data = StickersStateNewpack.deserialize(BytesIO(state.data))
        if not state_data.stickers or (len(state_data.stickers) == 1 and not state_data.stickers[0].emoji):
            return await send_bot_message(peer, _text_no_publish, entities=_text_no_publish_entities)

        await state.update_state(StickersBotState.NEWVIDEO_WAIT_ICON, None)
        return await send_bot_message(peer, _text_video_set_icon, entities=_text_video_set_icon_entities)
