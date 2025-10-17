from typing import cast, Callable, Awaitable

from piltover.app.bot_handlers.test_bot.ping_command import test_bot_ping_command
from piltover.db.models import Peer, Message

HANDLERS: dict[str, dict[str, Callable[[Peer, Message], Awaitable[Message | None]]]] = {
    "test_bot": {
        "ping": test_bot_ping_command,
    }
}


async def process_message_to_bot(peer: Peer, message: Message) -> Message | None:
    if not peer.user.bot or await peer.user.get_raw_username() not in HANDLERS:
        return None
    if message.message is None:
        return None
    text = cast(str, message.message)
    if not text.startswith("/"):
        return None

    bot_username = await peer.user.get_raw_username()

    command_name = text.split(" ", 1)[0][1:]
    if command_name not in HANDLERS[bot_username]:
        return None

    return await HANDLERS[bot_username][command_name](peer, message)
