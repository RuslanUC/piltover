from loguru import logger

import piltover.app.utils.updates_manager as upd
from piltover.app.bot_handlers.botfather.mybots_command import text_no_bots, text_choose_bot
from piltover.app.bot_handlers.botfather.utils import get_bot_selection_inline_keyboard
from piltover.db.models import Peer, Message, Bot
from piltover.db.models.bot import gen_bot_token
from piltover.tl import ReplyInlineMarkup, KeyboardButtonRow, KeyboardButtonCallback
from piltover.tl.types.messages import BotCallbackAnswer


__text_bot_selected = "Here it is: {name} @{username}.\nWhat do you want to do with the bot?"
__text_bot_token = "Here is the token for bot {name} @{username}:\n\n{token}"
__text_bot_token_revoked = "Token for the bot {name} @{username} has been revoked. New token is:\n\n{token}"


async def botfather_callback_query_handler(peer: Peer, message: Message, data: bytes) -> BotCallbackAnswer | None:
    logger.trace(data)

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

    if data.startswith(b"bots/"):
        try:
            bot_id = int(data[5:])
        except ValueError:
            return None

        bot = await Bot.get_or_none(owner=peer.owner, bot__id=bot_id).select_related("bot", "bot__usernames")
        if bot is None:
            return None

        message.message = __text_bot_selected.format(name=bot.bot.first_name, username=bot.bot.usernames.username)
        message.reply_markup = ReplyInlineMarkup(rows=[
            KeyboardButtonRow(buttons=[
                KeyboardButtonCallback(text=f"API Token", data=f"bots-token/{bot.bot_id}".encode("latin1")),
                KeyboardButtonCallback(text=f"TODO Edit Bot", data=f"bots-edit/{bot.bot_id}".encode("latin1")),
            ]),
            KeyboardButtonRow(buttons=[
                KeyboardButtonCallback(text=f"TODO Bot Settings", data=f"bots-settings/{bot.bot_id}".encode("latin1")),
                KeyboardButtonCallback(text=f"TODO Payments", data=f"bots-payments/{bot.bot_id}".encode("latin1")),
            ]),
            KeyboardButtonRow(buttons=[
                KeyboardButtonCallback(text=f"TODO Transfer Ownership", data=f"bots-transfer/{bot.bot_id}".encode("latin1")),
                KeyboardButtonCallback(text=f"TODO Delete Bot", data=f"bots-delete/{bot.bot_id}".encode("latin1")),
            ]),
            KeyboardButtonRow(buttons=[
                KeyboardButtonCallback(text=f"<- Back to Bot List", data=f"mybots".encode("latin1")),
            ]),
        ]).write()
        message.version += 1
        message.invalidate_reply_markup_cache()

        await message.save(update_fields=["message", "reply_markup", "version"])
        await upd.edit_message(peer.owner, {peer: message})

        return BotCallbackAnswer(cache_time=0)

    if data == b"mybots":
        rows = await get_bot_selection_inline_keyboard(peer.owner, 0)
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

    if data.startswith(b"bots-token/"):
        try:
            bot_id = int(data[11:])
        except ValueError:
            return None

        bot = await Bot.get_or_none(owner=peer.owner, bot__id=bot_id).select_related("bot", "bot__usernames")
        if bot is None:
            return None

        message.message = __text_bot_token.format(
            name=bot.bot.first_name, username=bot.bot.usernames.username, token=f"{bot.bot_id}:{bot.token_nonce}",
        )
        message.reply_markup = ReplyInlineMarkup(rows=[
            KeyboardButtonRow(buttons=[
                KeyboardButtonCallback(text=f"Revoke current token", data=f"bots-revoke/{bot.bot_id}".encode("latin1")),
            ]),
            KeyboardButtonRow(buttons=[
                KeyboardButtonCallback(text=f"<- Back to Bot", data=f"bots/{bot.bot_id}".encode("latin1")),
            ]),
        ]).write()
        message.version += 1
        message.invalidate_reply_markup_cache()

        await message.save(update_fields=["message", "reply_markup", "version"])
        await upd.edit_message(peer.owner, {peer: message})

        return BotCallbackAnswer(cache_time=0)

    if data.startswith(b"bots-revoke/"):
        try:
            bot_id = int(data[12:])
        except ValueError:
            return None

        bot = await Bot.get_or_none(owner=peer.owner, bot__id=bot_id).select_related("bot", "bot__usernames")
        if bot is None:
            return None

        bot.token_nonce = gen_bot_token()
        await bot.save(update_fields=["token_nonce"])

        message.message = __text_bot_token_revoked.format(
            name=bot.bot.first_name, username=bot.bot.usernames.username, token=f"{bot.bot_id}:{bot.token_nonce}",
        )
        message.reply_markup = ReplyInlineMarkup(rows=[
            KeyboardButtonRow(buttons=[
                KeyboardButtonCallback(text=f"<- Back to Bot", data=f"bots/{bot.bot_id}".encode("latin1")),
            ]),
        ]).write()
        message.version += 1
        message.invalidate_reply_markup_cache()

        await message.save(update_fields=["message", "reply_markup", "version"])
        await upd.edit_message(peer.owner, {peer: message})

        return BotCallbackAnswer(cache_time=0)

    logger.warning(f"Got unexpected callback data: {data} for BotFather")
    return None
