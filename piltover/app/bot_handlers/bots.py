from typing import cast, Callable, Awaitable

from piltover.app.bot_handlers.botfather.callback_handler import botfather_callback_query_handler
from piltover.app.bot_handlers.botfather.cancel_command import botfather_cancel_command
from piltover.app.bot_handlers.botfather.empty_command import botfather_empty_command
from piltover.app.bot_handlers.botfather.mybots_command import botfather_mybots_command
from piltover.app.bot_handlers.botfather.newbot_command import botfather_newbot_command
from piltover.app.bot_handlers.botfather.start_command import botfather_start_command
from piltover.app.bot_handlers.botfather.text_handler import botfather_text_message_handler
from piltover.app.bot_handlers.gif.inline_handler import gif_inline_query_handler
from piltover.app.bot_handlers.stickers.addemoji_command import stickers_addemoji_command
from piltover.app.bot_handlers.stickers.addsticker_command import stickers_addsticker_command
from piltover.app.bot_handlers.stickers.cancel_command import stickers_cancel_command
from piltover.app.bot_handlers.stickers.delpack_command import stickers_delpack_command
from piltover.app.bot_handlers.stickers.editsticker_command import stickers_editsticker_command
from piltover.app.bot_handlers.stickers.newemojipack_command import stickers_newemojipack_command
from piltover.app.bot_handlers.stickers.newpack_command import stickers_newpack_command
from piltover.app.bot_handlers.stickers.publish_command import stickers_publish_command
from piltover.app.bot_handlers.stickers.renamepack_command import stickers_renamepack_command
from piltover.app.bot_handlers.stickers.replacesticker_command import stickers_replacesticker_command
from piltover.app.bot_handlers.stickers.skip_command import stickers_skip_command
from piltover.app.bot_handlers.stickers.start_command import stickers_start_command
from piltover.app.bot_handlers.stickers.text_handler import stickers_text_message_handler
from piltover.app.bot_handlers.test_bot.ping_command import test_bot_ping_command
from piltover.db.models import Peer, Message, InlineQuery
from piltover.tl.types.messages import BotCallbackAnswer, BotResults


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
        "help": botfather_start_command,
        "newbot": botfather_newbot_command,
        "cancel": botfather_cancel_command,
        "mybots": botfather_mybots_command,
        "empty": botfather_empty_command,
    },
    "stickers": {
        "__text": stickers_text_message_handler,
        "start": stickers_start_command,
        "help": stickers_start_command,
        "newpack": stickers_newpack_command,
        "cancel": stickers_cancel_command,
        "publish": stickers_publish_command,
        "skip": stickers_skip_command,
        "addsticker": stickers_addsticker_command,
        "done": stickers_addsticker_command,
        "editsticker": stickers_editsticker_command,
        "delpack": stickers_delpack_command,
        "renamepack": stickers_renamepack_command,
        "replacesticker": stickers_replacesticker_command,
        "newemojipack": stickers_newemojipack_command,
        "addemoji": stickers_addemoji_command,
    }
}
CALLBACK_QUERY_HANDLERS: dict[str, Callable[[Peer, Message, bytes], Awaitable[BotCallbackAnswer | None]]] = {
    "botfather": botfather_callback_query_handler,
}
INLINE_QUERY_HANDLERS: dict[str, Callable[[InlineQuery], Awaitable[tuple[BotResults, bool] | None]]] = {
    "gif": gif_inline_query_handler,
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


async def process_callback_query(peer: Peer, message: Message, data: bytes) -> BotCallbackAnswer | None:
    if not peer.user.bot or await peer.user.get_raw_username() not in CALLBACK_QUERY_HANDLERS:
        return None
    if message.message is None:
        return None

    bot_username = await peer.user.get_raw_username()

    return await CALLBACK_QUERY_HANDLERS[bot_username](peer, message, data)


async def process_inline_query(inline_query: InlineQuery) -> tuple[BotResults, bool] | None:
    if not inline_query.bot.bot or await inline_query.bot.get_raw_username() not in INLINE_QUERY_HANDLERS:
        return None

    bot_username = await inline_query.bot.get_raw_username()

    return await INLINE_QUERY_HANDLERS[bot_username](inline_query)
