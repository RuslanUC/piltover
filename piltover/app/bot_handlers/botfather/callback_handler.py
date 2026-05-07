from loguru import logger
from tortoise.transactions import in_transaction

import piltover.app.utils.updates_manager as upd
from piltover.app.bot_handlers.botfather.mybots_command import text_no_bots, text_choose_bot
from piltover.app.bot_handlers.botfather.utils import get_bot_selection_inline_keyboard, send_bot_message
from piltover.app.utils.formatable_text_with_entities import FormatableTextWithEntities
from piltover.config import APP_CONFIG
from piltover.db.enums import BotFatherState
from piltover.db.models import Peer, Bot, BotInfo, BotFatherUserState, UserPhoto, BotCommand, MessageRef, User
from piltover.db.models.bot import bot_gen_token
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
__editbot_commands, __editbot_commands_entities = FormatableTextWithEntities("""
OK. Send me a list of commands for your bot. Please use this format:

command1 - Description
command2 - Another description

Send <c>/empty</c> to keep the list empty.
""".strip()).format()


async def botfather_callback_query_handler(peer: Peer, message: MessageRef, data: bytes) -> BotCallbackAnswer | None:
    logger.trace(data)

    if data.startswith(b"mybots/page/"):
        try:
            page = int(data[12:])
        except ValueError:
            return None
        if page < 0 or page > APP_CONFIG.max_bots_per_user // 6 - 1:
            return None

        rows = await get_bot_selection_inline_keyboard(peer.owner_id, page)
        if rows is None:
            message.content.message = text_no_bots
        else:
            message.content.message = text_choose_bot
            message.content.reply_markup = ReplyInlineMarkup(rows=rows).write()
        message.content.invalidate_reply_markup_cache()
        message.content.version += 1

        async with in_transaction():
            await message.content.save(update_fields=["message", "reply_markup", "version"])
        await upd.edit_message(peer.owner_id, {peer: message})

        return BotCallbackAnswer(cache_time=0)

    if data.startswith(b"bots/"):
        try:
            bot_id = int(data[5:])
        except ValueError:
            return None

        bot_info = await User.get_or_none(
            id=bot_id, bot_bot__owner_id=peer.owner_id
        ).select_related("username").values_list("first_name", "username__username")
        if bot_info is None:
            return None

        bot_first_name, bot_username = bot_info

        message.content.message, message.content.entities = __text_bot_selected.format(
            name=bot_first_name, username=bot_username,
        )
        message.content.reply_markup = ReplyInlineMarkup(rows=[
            KeyboardButtonRow(buttons=[
                KeyboardButtonCallback(text=f"API Token", data=f"bots-token/{bot_id}".encode("latin1")),
                KeyboardButtonCallback(text=f"Edit Bot", data=f"bots-edit/{bot_id}".encode("latin1")),
            ]),
            KeyboardButtonRow(buttons=[
                KeyboardButtonCallback(text=f"TODO Bot Settings", data=f"bots-settings/{bot_id}".encode("latin1")),
                KeyboardButtonCallback(text=f"TODO Payments", data=f"bots-payments/{bot_id}".encode("latin1")),
            ]),
            KeyboardButtonRow(buttons=[
                KeyboardButtonCallback(text=f"TODO Transfer Ownership", data=f"bots-transfer/{bot_id}".encode("latin1")),
                KeyboardButtonCallback(text=f"TODO Delete Bot", data=f"bots-delete/{bot_id}".encode("latin1")),
            ]),
            KeyboardButtonRow(buttons=[
                KeyboardButtonCallback(text=f"<- Back to Bot List", data=f"mybots".encode("latin1")),
            ]),
        ]).write()
        message.content.invalidate_reply_markup_cache()
        message.content.version += 1

        async with in_transaction():
            await message.content.save(update_fields=["message", "entities", "reply_markup", "version"])
        await upd.edit_message(peer.owner_id, {peer: message})

        return BotCallbackAnswer(cache_time=0)

    if data == b"mybots":
        rows = await get_bot_selection_inline_keyboard(peer.owner_id, 0)
        if rows is None:
            message.content.message = text_no_bots
        else:
            message.content.message = text_choose_bot
            message.content.reply_markup = ReplyInlineMarkup(rows=rows).write()
        message.content.invalidate_reply_markup_cache()
        message.content.version += 1

        async with in_transaction():
            await message.content.save(update_fields=["message", "reply_markup", "version"])
        await upd.edit_message(peer.owner_id, {peer: message})

        return BotCallbackAnswer(cache_time=0)

    if data.startswith(b"bots-token/"):
        try:
            bot_id = int(data[11:])
        except ValueError:
            return None

        bot_info = await Bot.get_or_none(
            bot_id=bot_id, owner_id=peer.owner_id
        ).select_related("bot", "bot__username").values_list(
            "token_nonce", "bot__first_name", "bot__username__username",
        )
        if bot_info is None:
            return None

        token_nonce, bot_first_name, bot_username = bot_info

        message.content.message, message.content.entities = __text_bot_token.format(
            name=bot_first_name, username=bot_username, token=f"{bot_id}:{token_nonce}",
        )
        message.content.reply_markup = ReplyInlineMarkup(rows=[
            KeyboardButtonRow(buttons=[
                KeyboardButtonCallback(text=f"Revoke current token", data=f"bots-revoke/{bot_id}".encode("latin1")),
            ]),
            KeyboardButtonRow(buttons=[
                KeyboardButtonCallback(text=f"<- Back to Bot", data=f"bots/{bot_id}".encode("latin1")),
            ]),
        ]).write()
        message.content.invalidate_reply_markup_cache()
        message.content.version += 1

        async with in_transaction():
            await message.content.save(update_fields=["message", "entities", "reply_markup", "version"])
        await upd.edit_message(peer.owner_id, {peer: message})

        return BotCallbackAnswer(cache_time=0)

    if data.startswith(b"bots-revoke/"):
        try:
            bot_id = int(data[12:])
        except ValueError:
            return None

        bot_q = Bot.filter(owner_id=peer.owner_id, bot_id=bot_id)

        if not await bot_q.exists():
            return None

        await bot_q.update(token_nonce=bot_gen_token())

        bot_info = await bot_q.get_or_none().select_related("bot", "bot__username").values_list(
            "token_nonce", "bot__first_name", "bot__username__username",
        )
        if bot_info is None:
            return None

        token_nonce, bot_first_name, bot_username = bot_info

        message.content.message, message.content.entities = __text_bot_token_revoked.format(
            name=bot_first_name, username=bot_username, token=f"{bot_id}:{token_nonce}",
        )
        message.content.reply_markup = ReplyInlineMarkup(rows=[
            KeyboardButtonRow(buttons=[
                KeyboardButtonCallback(text=f"<- Back to Bot", data=f"bots/{bot_id}".encode("latin1")),
            ]),
        ]).write()
        message.content.invalidate_reply_markup_cache()
        message.content.version += 1

        async with in_transaction():
            await message.content.save(update_fields=["message", "entities", "reply_markup", "version"])
        await upd.edit_message(peer.owner_id, {peer: message})

        return BotCallbackAnswer(cache_time=0)

    if data.startswith(b"bots-edit/"):
        try:
            bot_id = int(data[10:])
        except ValueError:
            return None

        bot_info = await User.get_or_none(
            id=bot_id, bot_bot__owner_id=peer.owner_id,
        ).select_related("username").values_list("first_name", "about", "username__username")
        if bot_info is None:
            return None

        bot_first_name, bot_about, bot_username = bot_info

        bot_info = await BotInfo.get_or_none(
            user_id=bot_id,
        ).only("description", "description_photo_id", "privacy_policy_url")
        has_photo = await UserPhoto.filter(user_id=bot_id).exists()
        commands_count = await BotCommand.filter(bot_id=bot_id).count()
        comm_plural_s = "s" if commands_count > 1 else ""

        description = bot_info.description if bot_info is not None and bot_info.description else "🚫"
        description_photo = (
            "has description picture"
            if bot_info is not None and bot_info.description_photo
            else "🚫 no description picture"
        )
        privacy_policy_url = (
            bot_info.privacy_policy_url
            if bot_info is not None and bot_info.privacy_policy_url
            else "🚫"
        )

        message.content.message, message.content.entities = __text_bot_edit_info.format(
            username=bot_username,
            name=bot_first_name,
            about=bot_about if bot_about else "🚫",
            description=description,
            picture=description_photo,
            profile_picture="🖼 has a botpic" if has_photo else "🚫 no botpic",
            commands=f"{commands_count} command{comm_plural_s}" if commands_count else "no commands yet",
            privacy_policy=privacy_policy_url,
        )
        message.content.reply_markup = ReplyInlineMarkup(rows=[
            KeyboardButtonRow(buttons=[
                KeyboardButtonCallback(text=f"Edit Name", data=f"bots-edit-name/{bot_id}".encode("latin1")),
                KeyboardButtonCallback(text=f"Edit About", data=f"bots-edit-about/{bot_id}".encode("latin1")),
            ]),
            KeyboardButtonRow(buttons=[
                KeyboardButtonCallback(text=f"Edit Description", data=f"bots-edit-desc/{bot_id}".encode("latin1")),
                KeyboardButtonCallback(text=f"🚫 Edit Description Picture", data=f"bots-edit-descpic/{bot_id}".encode("latin1")),
            ]),
            KeyboardButtonRow(buttons=[
                KeyboardButtonCallback(text=f"Edit Botpic", data=f"bots-edit-pic/{bot_id}".encode("latin1")),
                KeyboardButtonCallback(text=f"Edit Commands", data=f"bots-edit-commands/{bot_id}".encode("latin1")),
            ]),
            KeyboardButtonRow(buttons=[
                KeyboardButtonCallback(text=f"🚫 Edit Inline Placeholder", data=f"bots-edit-inline-placeholder/{bot_id}".encode("latin1")),
                KeyboardButtonCallback(text=f"Edit Privacy Policy", data=f"bots-edit-privacy/{bot_id}".encode("latin1")),
            ]),
            KeyboardButtonRow(buttons=[
                KeyboardButtonCallback(text=f"<- Back to Bot", data=f"bots/{bot_id}".encode("latin1")),
            ]),
        ]).write()
        message.content.invalidate_reply_markup_cache()
        message.content.version += 1

        async with in_transaction():
            await message.content.save(update_fields=["message", "entities", "reply_markup", "version"])
        await upd.edit_message(peer.owner_id, {peer: message})

        return BotCallbackAnswer(cache_time=0)

    if data.startswith(b"bots-edit-name/"):
        try:
            bot_id = int(data[15:])
        except ValueError:
            return None

        if not await Bot.filter(owner_id=peer.owner_id, bot_id=bot_id).exists():
            return None

        await BotFatherUserState.set_state(
            peer.owner_id, BotFatherState.EDITBOT_WAIT_NAME, BotfatherStateEditbot(bot_id=bot_id).serialize()
        )
        new_message = await send_bot_message(peer, __editbot_name)
        await upd.send_message(None, {peer: new_message}, False)

        return BotCallbackAnswer(cache_time=0)

    if data.startswith(b"bots-edit-about/"):
        try:
            bot_id = int(data[16:])
        except ValueError:
            return None

        if not await Bot.filter(owner_id=peer.owner_id, bot_id=bot_id).exists():
            return None

        await BotFatherUserState.set_state(
            peer.owner_id, BotFatherState.EDITBOT_WAIT_ABOUT, BotfatherStateEditbot(bot_id=bot_id).serialize()
        )
        new_message = await send_bot_message(peer, __editbot_about)
        await upd.send_message(None, {peer: new_message}, False)

        return BotCallbackAnswer(cache_time=0)

    if data.startswith(b"bots-edit-desc/"):
        try:
            bot_id = int(data[15:])
        except ValueError:
            return None

        if not await Bot.filter(owner_id=peer.owner_id, bot_id=bot_id).exists():
            return None

        await BotFatherUserState.set_state(
            peer.owner_id, BotFatherState.EDITBOT_WAIT_DESCRIPTION, BotfatherStateEditbot(bot_id=bot_id).serialize()
        )
        new_message = await send_bot_message(peer, __editbot_desc)
        await upd.send_message(None, {peer: new_message}, False)

        return BotCallbackAnswer(cache_time=0)

    if data.startswith(b"bots-edit-pic/"):
        try:
            bot_id = int(data[14:])
        except ValueError:
            return None

        if not await Bot.filter(owner_id=peer.owner_id, bot_id=bot_id).exists():
            return None

        await BotFatherUserState.set_state(
            peer.owner_id, BotFatherState.EDITBOT_WAIT_PHOTO, BotfatherStateEditbot(bot_id=bot_id).serialize()
        )
        new_message = await send_bot_message(peer, __editbot_photo)
        await upd.send_message(None, {peer: new_message}, False)

        return BotCallbackAnswer(cache_time=0)

    if data.startswith(b"bots-edit-privacy/"):
        try:
            bot_id = int(data[18:])
        except ValueError:
            return None

        if not await Bot.filter(owner_id=peer.owner_id, bot_id=bot_id).exists():
            return None

        await BotFatherUserState.set_state(
            peer.owner_id, BotFatherState.EDITBOT_WAIT_PRIVACY, BotfatherStateEditbot(bot_id=bot_id).serialize()
        )
        new_message = await send_bot_message(peer, __editbot_privacy, entities=__editbot_privacy_entities)
        await upd.send_message(None, {peer: new_message}, False)

        return BotCallbackAnswer(cache_time=0)

    if data.startswith(b"bots-edit-commands/"):
        try:
            bot_id = int(data[19:])
        except ValueError:
            return None

        if not await Bot.filter(owner_id=peer.owner_id, bot_id=bot_id).exists():
            return None

        await BotFatherUserState.set_state(
            peer.owner_id, BotFatherState.EDITBOT_WAIT_COMMANDS, BotfatherStateEditbot(bot_id=bot_id).serialize()
        )
        new_message = await send_bot_message(peer, __editbot_commands, entities=__editbot_commands_entities)
        await upd.send_message(None, {peer: new_message}, False)

        return BotCallbackAnswer(cache_time=0)

    logger.warning(f"Got unexpected callback data: {data} for BotFather")
    return None
