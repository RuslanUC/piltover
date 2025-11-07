from piltover.db.models import Username, User
from piltover.tl import KeyboardButtonRow, KeyboardButtonCallback


async def get_bot_selection_inline_keyboard(user: User, page: int) -> list[KeyboardButtonRow] | None:
    user_bots = await Username.filter(
        user__bots__owner=user, user__bot=True,
    ).order_by("-user__id").limit(7).offset(page * 6).values_list("username", "user__id")

    if not user_bots:
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
            data=f"mybots/bot/{bot_id}".encode("latin1"),
        ))

    if has_prev_page or has_next_page:
        rows.append(KeyboardButtonRow(buttons=[]))
    if has_prev_page:
        rows[-1].buttons.append(KeyboardButtonCallback(text=f"<-", data=f"mybots/page/{page - 1}".encode("latin1")))
    if has_next_page:
        rows[-1].buttons.append(KeyboardButtonCallback(text=f"->", data=f"mybots/page/{page + 1}".encode("latin1")))

    return rows
