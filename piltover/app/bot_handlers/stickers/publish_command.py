from io import BytesIO

from piltover.app.bot_handlers.stickers.utils import send_bot_message
from piltover.db.enums import StickersBotState
from piltover.db.models import Peer, Message, StickersBotUserState
from piltover.exceptions import Unreachable
from piltover.tl.types.internal_stickersbot import StickersStateNewpack

__text_no_publish = "You don't have any sticker sets yet. Use the /newpack command to create a new set first."
__text_set_icon = """
You can set an icon for your sticker set. Telegram apps will display it in the list of stickers in the sticker panel.

To set an icon, send me a square 100x100 image in PNG or WEBP format with a transparent layer.

You can /skip this step. If you do, apps will use the first sticker of your pack as its icon.
""".strip()
__text_set_icon_emoji = """
You can send me a custom emoji from your emoji set to use it as an icon. Telegram apps will display it in the list of emoji in the emoji panel.

You can also /skip this step. If you do, apps will use the first emoji of your pack as its icon.
""".strip()


async def stickers_publish_command(peer: Peer, _: Message) -> Message | None:
    state = await StickersBotUserState.get_or_none(user=peer.owner)
    if state is None or state.state not in (
            StickersBotState.NEWPACK_WAIT_IMAGE, StickersBotState.NEWPACK_WAIT_EMOJI,
            StickersBotState.NEWEMOJIPACK_WAIT_IMAGE, StickersBotState.NEWEMOJIPACK_WAIT_EMOJI,
    ):
        return await send_bot_message(peer, __text_no_publish)

    if state.state in (StickersBotState.NEWPACK_WAIT_IMAGE, StickersBotState.NEWPACK_WAIT_EMOJI):
        state_data = StickersStateNewpack.deserialize(BytesIO(state.data))
        if not state_data.stickers or (len(state_data.stickers) == 1 and not state_data.stickers[0].emoji):
            return await send_bot_message(peer, __text_no_publish)

        await state.update_state(StickersBotState.NEWPACK_WAIT_ICON, None)

        return await send_bot_message(peer, __text_set_icon)
    elif state.state in (StickersBotState.NEWEMOJIPACK_WAIT_IMAGE, StickersBotState.NEWEMOJIPACK_WAIT_EMOJI):
        state_data = StickersStateNewpack.deserialize(BytesIO(state.data))
        if not state_data.stickers or (len(state_data.stickers) == 1 and not state_data.stickers[0].emoji):
            return await send_bot_message(peer, __text_no_publish)

        await state.update_state(StickersBotState.NEWEMOJIPACK_WAIT_ICON, None)

        return await send_bot_message(peer, __text_set_icon_emoji)
    else:
        raise Unreachable

