from tortoise.expressions import Subquery

from piltover.db.models import Username, User, Bot, Peer, Message
from piltover.tl import KeyboardButtonRow, KeyboardButtonCallback


async def get_bot_selection_inline_keyboard(user: User, page: int) -> list[KeyboardButtonRow] | None:
    user_bots = await Username.filter(
        user__bot=True, user__id__in=Subquery(
            Bot.filter(owner=user).order_by("-bot__id").limit(7).offset(page * 6).values_list("bot__id")
        ),
    ).order_by("-user__id").values_list("username", "user__id")

    if not user_bots and not page:
        return None

    has_prev_page = page > 0
    has_next_page = len(user_bots) == 7
    user_bots = user_bots[:6]

    rows = []
    for idx, (username, bot_id) in enumerate(user_bots):
        if idx % 2 == 0:
            rows.append(KeyboardButtonRow(buttons=[]))
        rows[-1].buttons.append(KeyboardButtonCallback(
            text=f"@{username}",
            data=f"bots/{bot_id}".encode("latin1"),
        ))

    if has_prev_page or has_next_page:
        rows.append(KeyboardButtonRow(buttons=[]))
    if has_prev_page:
        rows[-1].buttons.append(KeyboardButtonCallback(text=f"<-", data=f"mybots/page/{page - 1}".encode("latin1")))
    if has_next_page:
        rows[-1].buttons.append(KeyboardButtonCallback(text=f"->", data=f"mybots/page/{page + 1}".encode("latin1")))

    return rows


async def send_bot_message(peer: Peer, text: str) -> Message:
    messages = await Message.create_for_peer(peer, None, None, peer.user, False, message=text)
    return messages[peer]
