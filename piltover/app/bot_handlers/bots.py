from typing import cast, Callable, Awaitable

from piltover.app.bot_handlers.botfather import BotfatherBotInteractionHandler
from piltover.app.bot_handlers.botfather.callback_handler import botfather_callback_query_handler
from piltover.app.bot_handlers.gif.inline_handler import gif_inline_query_handler
from piltover.app.bot_handlers.interaction_handler import BotInteractionHandler
from piltover.app.bot_handlers.stickers import StickersBotInteractionHandler
from piltover.app.bot_handlers.system import SystemBotInteractionHandler
from piltover.app.bot_handlers.test_bot import PingTestBotBotInteractionHandler
from piltover.db.models import Peer, InlineQuery, InlineQueryResult, InlineQueryResultItem, MessageRef
from piltover.tl.types.messages import BotCallbackAnswer, BotResults


async def _awaitable_none(_p: Peer, _m: MessageRef) -> None:
    return None


HANDLERS: dict[str, BotInteractionHandler] = {
    "test_bot": PingTestBotBotInteractionHandler(),
    "system": SystemBotInteractionHandler(),
    "botfather": BotfatherBotInteractionHandler(),
    "stickers": StickersBotInteractionHandler(),
}
CALLBACK_QUERY_HANDLERS: dict[str, Callable[[Peer, MessageRef, bytes], Awaitable[BotCallbackAnswer | None]]] = {
    "botfather": botfather_callback_query_handler,
}
INLINE_QUERY_HANDLERS: dict[str, Callable[[InlineQuery], Awaitable[tuple[BotResults, bool] | None]]] = {
    "gif": gif_inline_query_handler,
}


async def process_message_to_bot(peer: Peer, message: MessageRef) -> MessageRef | None:
    if not peer.user.bot or await peer.user.get_raw_username() not in HANDLERS:
        return None
    if message.content.message is None:
        return None

    bot_username = await peer.user.get_raw_username()
    handler = HANDLERS[bot_username]

    text = cast(str, message.content.message)
    if not text.startswith("/"):
        return await handler.handle_text(peer, message)

    command_name = text.split(" ", 1)[0][1:]
    return await handler.handle_command(command_name, peer, message)


async def process_callback_query(peer: Peer, message: MessageRef, data: bytes) -> BotCallbackAnswer | None:
    if not peer.user.bot or await peer.user.get_raw_username() not in CALLBACK_QUERY_HANDLERS:
        return None
    if message.content.message is None:
        return None

    bot_username = await peer.user.get_raw_username()

    return await CALLBACK_QUERY_HANDLERS[bot_username](peer, message, data)


async def process_inline_query(
        inline_query: InlineQuery,
) -> tuple[InlineQueryResult, list[InlineQueryResultItem]] | None:
    if not inline_query.bot.bot or await inline_query.bot.get_raw_username() not in INLINE_QUERY_HANDLERS:
        return None

    bot_username = await inline_query.bot.get_raw_username()

    return await INLINE_QUERY_HANDLERS[bot_username](inline_query)
