from loguru import logger

import piltover.app.utils.updates_manager as upd
from piltover.app.bot_handlers.botfather.mybots_command import text_no_bots, text_choose_bot
from piltover.app.bot_handlers.botfather.utils import get_bot_selection_inline_keyboard, send_bot_message
from piltover.app.utils.formatable_text_with_entities import FormatableTextWithEntities
from piltover.db.enums import BotFatherState
from piltover.db.models import Peer, Message, Bot, BotInfo, BotFatherUserState, UserPhoto
from piltover.db.models.bot import gen_bot_token
from piltover.tl import ReplyInlineMarkup, KeyboardButtonRow, KeyboardButtonCallback
from piltover.tl.types.internal_botfather import BotfatherStateEditbot
from piltover.tl.types.messages import BotCallbackAnswer

__text_bot_selected = FormatableTextWithEntities(
    "Here it is: {name} <u>@{username}</u>.\nWhat do you want to do with the bot?"
)
__text_bot_token = FormatableTextWithEntities(
    "Here is the token for bot {name} <u>@{username}</u>:\n\n`{token}`"
)
__text_bot_token_revoked = FormatableTextWithEntities(
    "Token for the bot {name} <u>@{username}</u> has been revoked. New token is:\n\n`{token}`"
)
__text_bot_edit_info = FormatableTextWithEntities("""
Edit <u>@{username}</u> info.

**Name**: {name}
**About**: {about}
**Description**: {description}
**Description picture**: {picture}
**Botpic**: {profile_picture}
**Commands**: {commands}
**Privacy Policy**: {privacy_policy}
""".strip())
__editbot_name = "OK. Send me the new name for your bot."
__editbot_about = (
    "OK. Send me the new 'About' text. "
    "People will see this text on the bot's profile page and it will be sent together with a link "
    "to your bot when they share it with someone."
)
__editbot_desc = (
    "OK. Send me the new description for the bot. "
    "People will see this description when they open a chat with your bot, in a block titled 'What can this bot do?'."
)
__editbot_photo = "OK. Send me the new profile photo for the bot."
__editbot_privacy, __editbot_privacy_entities = FormatableTextWithEntities("""
Send me a public URL to the new Privacy Policy for the bot or use <c>/empty</c> to remove the current one.

If you don't specify a Privacy Policy, the Standard Privacy Policy for Bots and Mini Apps will apply.
""".strip()).format()


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

        message.message, message.entities = __text_bot_selected.format(
            name=bot.bot.first_name, username=bot.bot.usernames.username,
        )
        message.reply_markup = ReplyInlineMarkup(rows=[
            KeyboardButtonRow(buttons=[
                KeyboardButtonCallback(text=f"API Token", data=f"bots-token/{bot.bot_id}".encode("latin1")),
                KeyboardButtonCallback(text=f"Edit Bot", data=f"bots-edit/{bot.bot_id}".encode("latin1")),
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

        await message.save(update_fields=["message", "entities", "reply_markup", "version"])
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

        message.message, message.entities = __text_bot_token.format(
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

        await message.save(update_fields=["message", "entities", "reply_markup", "version"])
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

        message.message, message.entities = __text_bot_token_revoked.format(
            name=bot.bot.first_name, username=bot.bot.usernames.username, token=f"{bot.bot_id}:{bot.token_nonce}",
        )
        message.reply_markup = ReplyInlineMarkup(rows=[
            KeyboardButtonRow(buttons=[
                KeyboardButtonCallback(text=f"<- Back to Bot", data=f"bots/{bot.bot_id}".encode("latin1")),
            ]),
        ]).write()
        message.version += 1
        message.invalidate_reply_markup_cache()

        await message.save(update_fields=["message", "entities", "reply_markup", "version"])
        await upd.edit_message(peer.owner, {peer: message})

        return BotCallbackAnswer(cache_time=0)

    if data.startswith(b"bots-edit/"):
        try:
            bot_id = int(data[10:])
        except ValueError:
            return None

        bot = await Bot.get_or_none(owner=peer.owner, bot__id=bot_id).select_related("bot", "bot__usernames")
        if bot is None:
            return None

        bot_info, _ = await BotInfo.get_or_create(user=bot.bot)
        has_photo = await UserPhoto.filter(user=bot.bot).exists()

        message.message, message.entities = __text_bot_edit_info.format(
            username=bot.bot.usernames.username,
            name=bot.bot.first_name,
            about=bot.bot.about if bot.bot.about else "🚫",
            description=bot_info.description if bot_info.description else "🚫",
            picture="has description picture" if bot_info.description_photo else "🚫 no description picture",
            profile_picture="🖼 has a botpic" if has_photo else "🚫 no botpic",
            # TODO: commands
            commands="no commands yet",
            privacy_policy=bot_info.privacy_policy_url if bot_info.privacy_policy_url else "🚫",
        )
        message.reply_markup = ReplyInlineMarkup(rows=[
            KeyboardButtonRow(buttons=[
                KeyboardButtonCallback(text=f"Edit Name", data=f"bots-edit-name/{bot.bot_id}".encode("latin1")),
                KeyboardButtonCallback(text=f"Edit About", data=f"bots-edit-about/{bot.bot_id}".encode("latin1")),
            ]),
            KeyboardButtonRow(buttons=[
                KeyboardButtonCallback(text=f"Edit Description", data=f"bots-edit-desc/{bot.bot_id}".encode("latin1")),
                KeyboardButtonCallback(text=f"🚫 Edit Description Picture", data=f"bots-edit-descpic/{bot.bot_id}".encode("latin1")),
            ]),
            KeyboardButtonRow(buttons=[
                KeyboardButtonCallback(text=f"Edit Botpic", data=f"bots-edit-pic/{bot.bot_id}".encode("latin1")),
                KeyboardButtonCallback(text=f"🚫 Edit Commands", data=f"bots-edit-commands/{bot.bot_id}".encode("latin1")),
            ]),
            KeyboardButtonRow(buttons=[
                KeyboardButtonCallback(text=f"🚫 Edit Inline Placeholder", data=f"bots-edit-inline-placeholder/{bot.bot_id}".encode("latin1")),
                KeyboardButtonCallback(text=f"Edit Privacy Policy", data=f"bots-edit-privacy/{bot.bot_id}".encode("latin1")),
            ]),
            KeyboardButtonRow(buttons=[
                KeyboardButtonCallback(text=f"<- Back to Bot", data=f"bots/{bot.bot_id}".encode("latin1")),
            ]),
        ]).write()
        message.version += 1
        message.invalidate_reply_markup_cache()

        await message.save(update_fields=["message", "entities", "reply_markup", "version"])
        await upd.edit_message(peer.owner, {peer: message})

        return BotCallbackAnswer(cache_time=0)

    if data.startswith(b"bots-edit-name/"):
        try:
            bot_id = int(data[15:])
        except ValueError:
            return None

        if not await Bot.filter(owner=peer.owner, bot__id=bot_id).exists():
            return None

        await BotFatherUserState.set_state(
            peer.owner, BotFatherState.EDITBOT_WAIT_NAME, BotfatherStateEditbot(bot_id=bot_id).serialize()
        )
        message = await send_bot_message(peer, __editbot_name)
        await upd.send_message(None, {peer: message}, False)

        return BotCallbackAnswer(cache_time=0)

    if data.startswith(b"bots-edit-about/"):
        try:
            bot_id = int(data[16:])
        except ValueError:
            return None

        if not await Bot.filter(owner=peer.owner, bot__id=bot_id).exists():
            return None

        await BotFatherUserState.set_state(
            peer.owner, BotFatherState.EDITBOT_WAIT_ABOUT, BotfatherStateEditbot(bot_id=bot_id).serialize()
        )
        message = await send_bot_message(peer, __editbot_about)
        await upd.send_message(None, {peer: message}, False)

        return BotCallbackAnswer(cache_time=0)

    if data.startswith(b"bots-edit-desc/"):
        try:
            bot_id = int(data[15:])
        except ValueError:
            return None

        if not await Bot.filter(owner=peer.owner, bot__id=bot_id).exists():
            return None

        await BotFatherUserState.set_state(
            peer.owner, BotFatherState.EDITBOT_WAIT_DESCRIPTION, BotfatherStateEditbot(bot_id=bot_id).serialize()
        )
        message = await send_bot_message(peer, __editbot_desc)
        await upd.send_message(None, {peer: message}, False)

        return BotCallbackAnswer(cache_time=0)

    if data.startswith(b"bots-edit-pic/"):
        try:
            bot_id = int(data[14:])
        except ValueError:
            return None

        if not await Bot.filter(owner=peer.owner, bot__id=bot_id).exists():
            return None

        await BotFatherUserState.set_state(
            peer.owner, BotFatherState.EDITBOT_WAIT_PHOTO, BotfatherStateEditbot(bot_id=bot_id).serialize()
        )
        message = await send_bot_message(peer, __editbot_photo)
        await upd.send_message(None, {peer: message}, False)

        return BotCallbackAnswer(cache_time=0)

    if data.startswith(b"bots-edit-privacy/"):
        try:
            bot_id = int(data[18:])
        except ValueError:
            return None

        if not await Bot.filter(owner=peer.owner, bot__id=bot_id).exists():
            return None

        await BotFatherUserState.set_state(
            peer.owner, BotFatherState.EDITBOT_WAIT_PRIVACY, BotfatherStateEditbot(bot_id=bot_id).serialize()
        )
        message = await send_bot_message(peer, __editbot_privacy, entities=__editbot_privacy_entities)
        await upd.send_message(None, {peer: message}, False)

        return BotCallbackAnswer(cache_time=0)

    logger.warning(f"Got unexpected callback data: {data} for BotFather")
    return None
