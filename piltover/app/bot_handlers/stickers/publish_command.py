from io import BytesIO

from piltover.app.bot_handlers.stickers.utils import send_bot_message
from piltover.app.utils.formatable_text_with_entities import FormatableTextWithEntities
from piltover.db.enums import StickersBotState
from piltover.db.models import Peer, StickersBotUserState, MessageRef
from piltover.exceptions import Unreachable
from piltover.tl.types.internal_stickersbot import StickersStateNewpack, StickersStateNewemojipack

__text_no_publish, __text_no_publish_entities = FormatableTextWithEntities(
    "You don't have any sticker sets yet. Use the <c>/newpack</c> command to create a new set first."
).format()
__text_set_icon, __text_set_icon_entities = FormatableTextWithEntities("""
You can set an icon for your sticker set. Telegram apps will display it in the list of stickers in the sticker panel.

To set an icon, send me a square 100x100 image in PNG or WEBP format with a transparent layer.

You can <c>/skip</c> this step. If you do, apps will use the first sticker of your pack as its icon.
""".strip()).format()
__text_set_icon_emoji, __text_set_icon_emoji_entities = FormatableTextWithEntities("""
You can send me a custom emoji from your emoji set to use it as an icon. Telegram apps will display it in the list of emoji in the emoji panel.

You can also <c>/skip</c> this step. If you do, apps will use the first emoji of your pack as its icon.
""".strip()).format()


async def stickers_publish_command(peer: Peer, _: MessageRef) -> MessageRef | None:
    state = await StickersBotUserState.get_or_none(user=peer.owner)
    if state is None or state.state not in (
            StickersBotState.NEWPACK_WAIT_IMAGE, StickersBotState.NEWPACK_WAIT_EMOJI,
            StickersBotState.NEWEMOJIPACK_WAIT_IMAGE, StickersBotState.NEWEMOJIPACK_WAIT_EMOJI,
    ):
        return await send_bot_message(peer, __text_no_publish, entities=__text_no_publish_entities)

    if state.state in (StickersBotState.NEWPACK_WAIT_IMAGE, StickersBotState.NEWPACK_WAIT_EMOJI):
        state_data = StickersStateNewpack.deserialize(BytesIO(state.data))
        if not state_data.stickers or (len(state_data.stickers) == 1 and not state_data.stickers[0].emoji):
            return await send_bot_message(peer, __text_no_publish, entities=__text_no_publish_entities)

        await state.update_state(StickersBotState.NEWPACK_WAIT_ICON, None)

        return await send_bot_message(peer, __text_set_icon, entities=__text_set_icon_entities)
    elif state.state in (StickersBotState.NEWEMOJIPACK_WAIT_IMAGE, StickersBotState.NEWEMOJIPACK_WAIT_EMOJI):
        state_data = StickersStateNewemojipack.deserialize(BytesIO(state.data))
        if not state_data.stickers or (len(state_data.stickers) == 1 and not state_data.stickers[0].emoji):
            return await send_bot_message(peer, __text_no_publish, entities=__text_no_publish_entities)

        await state.update_state(StickersBotState.NEWEMOJIPACK_WAIT_ICON, None)

        return await send_bot_message(peer, __text_set_icon_emoji, entities=__text_set_icon_emoji_entities)
    else:
        raise Unreachable

