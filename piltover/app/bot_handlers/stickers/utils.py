from tortoise.expressions import Q

from piltover.db.models import User, Peer, Stickerset, MessageRef
from piltover.tl import KeyboardButtonRow, KeyboardButton, ReplyInlineMarkup, ReplyKeyboardMarkup, ReplyKeyboardHide


async def get_stickerset_selection_keyboard(user: User, emoji: bool | None = False) -> list[KeyboardButtonRow] | None:
    query = Q(owner=user)
    if emoji is not None:
        query &= Q(emoji=emoji)
    stickersets = await Stickerset.filter(query).order_by("-id").values_list("short_name", flat=True)

    if not stickersets:
        return None

    rows = []
    for idx, short_name in enumerate(stickersets):
        if idx % 2 == 0:
            rows.append(KeyboardButtonRow(buttons=[]))
        rows[-1].buttons.append(KeyboardButton(text=short_name))

    return rows


async def send_bot_message(
        peer: Peer, text: str, keyboard: ReplyInlineMarkup | ReplyKeyboardMarkup | ReplyKeyboardHide | None = None,
        entities: list[dict[str, str | int]] | None = None,
) -> MessageRef:
    messages = await MessageRef.create_for_peer(
        peer, peer.user, opposite=False,
        message=text, reply_markup=keyboard.write() if keyboard else None, entities=entities,
    )
    return messages[peer]


EMOJI_PACK_TYPES_KEYBOARD = ReplyKeyboardMarkup(
    rows=[
        KeyboardButtonRow(
            buttons=[KeyboardButton(text="Animated emoji")],
        ),
        KeyboardButtonRow(
            buttons=[KeyboardButton(text="Video emoji")],
        ),
        KeyboardButtonRow(
            buttons=[KeyboardButton(text="Static emoji")],
        ),
    ]
)
