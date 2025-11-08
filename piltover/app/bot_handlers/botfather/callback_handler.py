from loguru import logger

import piltover.app.utils.updates_manager as upd
from piltover.app.bot_handlers.botfather.mybots_command import text_no_bots, text_choose_bot
from piltover.app.bot_handlers.botfather.utils import get_bot_selection_inline_keyboard
from piltover.db.models import Peer, Message
from piltover.tl import ReplyInlineMarkup
from piltover.tl.types.messages import BotCallbackAnswer


async def botfather_callback_query_handler(peer: Peer, message: Message, data: bytes) -> BotCallbackAnswer | None:
    if data.startswith(b"mybots/page/"):
        try:
            page = int(data[12:])
        except ValueError:
            return None
        # TODO: move 24 to variable `MAX_BOTS_PER_USER`
        if page < 0 or page > 24 // 6 - 1:
            return None

        rows = await get_bot_selection_inline_keyboard(peer.owner, page)
        if rows is None:
            message.message = text_no_bots
        else:
            message.message = text_choose_bot
            message.reply_markup = ReplyInlineMarkup(rows=rows).write()
        message.version += 1
        message.invalidate_reply_markup_cache()

        await message.save(update_fields=["message", "reply_markup", "version"])
        await upd.edit_message(peer.owner, {peer: message})

        return BotCallbackAnswer(cache_time=0)

    logger.warning(f"Got unexpected callback data: {data} for BotFather")
    return None
