from piltover.db.models import User, Peer, Message, Stickerset
from piltover.tl import KeyboardButtonRow, KeyboardButton, ReplyInlineMarkup, ReplyKeyboardMarkup


async def get_stickerset_selection_keyboard(user: User) -> list[KeyboardButtonRow] | None:
    stickersets = await Stickerset.filter(owner=user).order_by("-id").values_list("short_name")

    if not stickersets:
        return None

    rows = []
    for idx, short_name in enumerate(stickersets):
        if idx % 2 == 0:
            rows.append(KeyboardButtonRow(buttons=[]))
        rows[-1].buttons.append(KeyboardButton(text=short_name))

    return rows


async def send_bot_message(
        peer: Peer, text: str, keyboard: ReplyInlineMarkup | ReplyKeyboardMarkup | None = None
) -> Message:
    messages = await Message.create_for_peer(
        peer, None, None, peer.user, False,
        message=text, reply_markup=keyboard.write() if keyboard else None,
    )
    return messages[peer]
