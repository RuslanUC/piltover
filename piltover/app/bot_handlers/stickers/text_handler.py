from datetime import datetime, UTC
from io import BytesIO

from piltover.db.enums import StickersBotState, MediaType
from piltover.db.models import Peer, Message
from piltover.db.models.stickers_state import StickersBotUserState
from piltover.tl.types.internal_stickersbot import StickersStateNewpack

__newpack_send_sticker = """
Alright! Now send me the sticker. The image file should be in PNG or WEBP format with a transparent layer and must fit into a 512x512 square (one of the sides must be 512px and the other 512px or less).

I recommend using Telegram for Web/Desktop when uploading stickers.
"""
__newpack_invalid_name = "Sorry, this title is unacceptable."
__newpack_invalid_file = "Please send me your sticker image as a file."
__newpack_send_emoji = """
Thanks! Now send me an emoji that corresponds to your first sticker.

You can list several emoji in one message, but I recommend using no more than two per sticker.
"""


async def stickers_text_message_handler(peer: Peer, message: Message) -> Message | None:
    state = await StickersBotUserState.get_or_none(user=peer.owner)
    if state is None:
        return None

    if state.state is StickersBotState.NEWPACK_WAIT_NAME:
        pack_name = message.message
        if len(pack_name) > 64:
            messages = await Message.create_for_peer(peer, None, None, peer.user, False, message=__newpack_invalid_name)
            return messages[peer]

        state.state = StickersBotState.NEWPACK_WAIT_IMAGE
        state.data = StickersStateNewpack(name=pack_name, stickers=[]).serialize()
        state.last_access = datetime.now(UTC)
        await state.save(update_fields=["state", "data", "last_access"])

        messages = await Message.create_for_peer(peer, None, None, peer.user, False, message=__newpack_send_sticker)
        return messages[peer]

    if state.state is StickersBotState.NEWPACK_WAIT_IMAGE:
        if message.media is None:
            messages = await Message.create_for_peer(peer, None, None, peer.user, False, message=__newpack_invalid_file)
            return messages[peer]
        if message.media.type is not MediaType.DOCUMENT:
            messages = await Message.create_for_peer(peer, None, None, peer.user, False, message=__newpack_invalid_file)
            return messages[peer]

        state_data = StickersStateNewpack.deserialize(BytesIO(state.data))
        if state_data.stickers:
            ...
        else:
            ...
