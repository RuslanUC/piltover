from piltover.app.bot_handlers.botfather.utils import get_bot_selection_inline_keyboard
from piltover.db.models import Peer, Message
from piltover.tl import ReplyInlineMarkup

__text = """
Choose a bot from the list below:
"""
__text_no_bots = """
No bots :( (TODO: use proper message from real BotFather)
"""


async def botfather_mybots_command(peer: Peer, _: Message) -> Message | None:
    rows = await get_bot_selection_inline_keyboard(peer.owner, 0)
    if rows is None:
        messages = await Message.create_for_peer(peer, None, None, peer.user, False, message=__text_no_bots)
        return messages[peer]

    messages = await Message.create_for_peer(
        peer, None, None, peer.user, False, message=__text, reply_markup=ReplyInlineMarkup(
            rows=rows,
        ),
    )
    return messages[peer]
