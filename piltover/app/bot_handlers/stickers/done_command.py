from piltover.app.bot_handlers.stickers.utils import send_bot_message
from piltover.db.enums import StickersBotState
from piltover.db.models import Peer, Message, StickersBotUserState

__text = "OK, well done!"
__text_no_done = "This command was a bit out of place here. Are you sure you meant that?"


async def stickers_done_command(peer: Peer, _: Message) -> Message | None:
    state = await StickersBotUserState.get_or_none(user=peer.owner)
    if state is None:
        return await send_bot_message(peer, __text_no_done)

    if state.state in (
            StickersBotState.ADDSTICKER_WAIT_IMAGE, StickersBotState.ADDSTICKER_WAIT_EMOJI,
            StickersBotState.ADDEMOJI_WAIT_IMAGE, StickersBotState.ADDEMOJI_WAIT_EMOJI
    ):
        await state.delete()
        return await send_bot_message(peer, __text)

    return await send_bot_message(peer, __text_no_done)
