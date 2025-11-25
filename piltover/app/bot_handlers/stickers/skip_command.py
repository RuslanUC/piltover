from piltover.app.bot_handlers.stickers.utils import send_bot_message
from piltover.db.enums import StickersBotState
from piltover.db.models import Peer, Message, StickersBotUserState

__text_no_skip = "Sorry, this step can't be skipped"
__text_icon_skipped = """
Please provide a short name for your set. I'll use it to create a link that you can share with friends and followers.

For example, this set has the short name 'Animals': https://telegram.me/addstickers/Animals
""".strip()


async def stickers_skip_command(peer: Peer, _: Message) -> Message | None:
    state = await StickersBotUserState.get_or_none(user=peer.owner)
    if state is None:
        return await send_bot_message(peer, __text_no_skip)

    if state.state is StickersBotState.NEWPACK_WAIT_ICON:
        await state.update_state(StickersBotState.NEWPACK_WAIT_SHORT_NAME, None)
        return await send_bot_message(peer, __text_icon_skipped)

    return await send_bot_message(peer, __text_no_skip)
