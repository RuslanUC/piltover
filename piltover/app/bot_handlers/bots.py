from typing import cast, Callable, Awaitable

from piltover.app.bot_handlers.botfather.newbot_command import botfather_newbot_command
from piltover.app.bot_handlers.botfather.start_command import botfather_start_command
from piltover.app.bot_handlers.botfather.text_handler import botfather_text_message_handler
from piltover.app.bot_handlers.test_bot.ping_command import test_bot_ping_command
from piltover.db.models import Peer, Message


async def _awaitable_none(_p: Peer, _m: Message) -> None:
    return None


HANDLERS: dict[str, dict[str, Callable[[Peer, Message], Awaitable[Message | None]]]] = {
    "test_bot": {
        "__text": _awaitable_none,
        "ping": test_bot_ping_command,
    },
    "botfather": {
        "__text": botfather_text_message_handler,
        "start": botfather_start_command,
        "newbot": botfather_newbot_command,
    }
}


async def process_message_to_bot(peer: Peer, message: Message) -> Message | None:
    if not peer.user.bot or await peer.user.get_raw_username() not in HANDLERS:
        return None
    if message.message is None:
        return None

    bot_username = await peer.user.get_raw_username()

    text = cast(str, message.message)
    if not text.startswith("/"):
        return await HANDLERS[bot_username]["__text"](peer, message)

    command_name = text.split(" ", 1)[0][1:]
    if command_name not in HANDLERS[bot_username]:
        return await HANDLERS[bot_username]["__text"](peer, message)

    return await HANDLERS[bot_username][command_name](peer, message)
