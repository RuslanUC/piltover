from asyncio import sleep
from io import BytesIO
from urllib.parse import urlparse

from tortoise.transactions import in_transaction

from piltover.app.bot_handlers.botfather.utils import send_bot_message
from piltover.app.utils.formatable_text_with_entities import FormatableTextWithEntities
from piltover.app.utils.utils import is_username_valid
from piltover.context import request_ctx
from piltover.db.enums import BotFatherState, MediaType
from piltover.db.models import Peer, Message, BotFatherUserState, Username, User, Bot, BotInfo, UserPhoto, BotCommand, \
    State
from piltover.tl.types.internal_botfather import BotfatherStateNewbot, BotfatherStateEditbot

__bot_name_invalid = "Sorry, this isn't a proper name for a bot."
__bot_wait_username = ("Good. Now let's choose a username for your bot. It must end in `bot`. "
                       "Like this, for example: TetrisBot or tetris_bot.")
__bot_username_invalid = "Sorry, this username is invalid."
__bot_username_ends_bot = "Sorry, the username must end in `bot`. E.g. Tetris_bot or Tetrisbot."
__bot_username_taken = "Sorry, this username is already taken. Please try something different."
__bot_created = FormatableTextWithEntities("""
Done! Congratulations on your new bot. You will find it at <a>t.me/{username}</a>. You can now add a description, about section and profile picture for your bot, see <c>/help</c> for a list of commands. By the way, when you've finished creating your cool bot, ping our Bot Support if you want a better username for it. Just make sure the bot is fully operational before you do this.

Use this token to access the HTTP API:
`{token}`
Keep your token secure and store it safely, it can be used by anyone to control your bot.

For a description of the Bot API, see this page: <a>https://core.telegram.org/bots/api</a>
""".strip())
__bot_name_updated, __bot_name_updated_entities = FormatableTextWithEntities(
    "Success! Name updated. <c>/help</c>",
).format()
__bot_about_invalid = "Sorry, the about info you provided is invalid. It must not exceed 120 characters."
__bot_about_updated, __bot_about_updated_entities = FormatableTextWithEntities(
    "Success! About section updated. <c>/help</c>",
).format()
__bot_desc_invalid = (
    "Sorry the description you provided is invalid. "
    "A description may not exceed 120 characters (line breaks included)."
)
__bot_desc_updated, __bot_desc_updated_entities = FormatableTextWithEntities(
    "Success! Description updated. You will be able to see the changes within a few minutes. <c>/help</c>",
).format()
__bot_photo_invalid = "Please send me the picture as a 'Photo', not as a 'File'."
__bot_photo_updated, __bot_photo_updated_entities = FormatableTextWithEntities(
    "Success! Profile photo updated. <c>/help</c>",
).format()
__bot_privacy_invalid = "Please send me a valid URL."
_bot_privacy_updated, _bot_privacy_updated_entities = FormatableTextWithEntities(
    "Success! Privacy policy updated. <c>/help</c>",
).format()
_bot_commands_updated, _bot_commands_updated_entities = FormatableTextWithEntities(
    "Success! Command list updated. <c>/help</c>",
).format()
__bot_commands_invalid, __bot_commands_invalid_entities = FormatableTextWithEntities("""
Sorry, the list of commands is invalid. Please use this format:

command1 - Description
command2 - Another description

Send <c>/empty</c> to keep the list empty.
""".strip()).format()


async def botfather_text_message_handler(peer: Peer, message: Message) -> Message | None:
    state = await BotFatherUserState.get_or_none(user=peer.owner)
    if state is None:
        return None

    if state.state is BotFatherState.NEWBOT_WAIT_NAME:
        first_name = message.message
        if len(first_name) > 64:
            return await send_bot_message(peer, __bot_name_invalid)

        await state.update_state(BotFatherState.NEWBOT_WAIT_USERNAME, BotfatherStateNewbot(name=first_name).serialize())

        return await send_bot_message(peer, __bot_wait_username)

    if state.state is BotFatherState.NEWBOT_WAIT_USERNAME:
        username = message.message
        if not is_username_valid(username):
            return await send_bot_message(peer, __bot_username_invalid)
        if not username.endswith("bot"):
            return await send_bot_message(peer, __bot_username_ends_bot)
        if await Username.filter(username=username).exists():
            return await send_bot_message(peer, __bot_username_taken)

        state_data = BotfatherStateNewbot.deserialize(BytesIO(state.data))

        async with in_transaction():
            bot_user = await User.create(phone_number=None, first_name=state_data.name, bot=True)
            await State.create(user=bot_user)
            await Username.create(user=bot_user, username=username)
            bot = await Bot.create(owner=peer.owner, bot=bot_user)
            await state.delete()

        text, entities = __bot_created.format(username=username, token=f"{bot_user.id}:{bot.token_nonce}")
        return await send_bot_message(peer, text, entities=entities)

    if state.state is BotFatherState.EDITBOT_WAIT_NAME:
        first_name = message.message
        if len(first_name) > 64:
            return await send_bot_message(peer, __bot_name_invalid)

        state_data = BotfatherStateEditbot.deserialize(BytesIO(state.data))
        bot = await Bot.get_or_none(bot__id=state_data.bot_id, owner=peer.owner).select_related("bot")
        if bot is None:
            return await send_bot_message(peer, "Bot does not exist (?)")

        async with in_transaction():
            bot.bot.first_name = first_name
            bot.bot.version += 1
            await bot.save(update_fields=["first_name", "version"])
            await state.delete()

        return await send_bot_message(peer, __bot_name_updated, entities=__bot_name_updated_entities)

    if state.state is BotFatherState.EDITBOT_WAIT_ABOUT:
        about = message.message
        if len(about) > 120:
            return await send_bot_message(peer, __bot_about_invalid)

        state_data = BotfatherStateEditbot.deserialize(BytesIO(state.data))
        bot = await Bot.get_or_none(bot__id=state_data.bot_id, owner=peer.owner).select_related("bot")
        if bot is None:
            return await send_bot_message(peer, "Bot does not exist (?)")

        async with in_transaction():
            bot.bot.about = about
            bot.bot.version += 1
            await bot.save(update_fields=["about", "version"])
            await state.delete()

        return await send_bot_message(peer, __bot_about_updated, entities=__bot_about_updated_entities)

    if state.state is BotFatherState.EDITBOT_WAIT_DESCRIPTION:
        description = message.message
        if len(description) > 120:
            return await send_bot_message(peer, __bot_desc_invalid)

        state_data = BotfatherStateEditbot.deserialize(BytesIO(state.data))
        bot = await Bot.get_or_none(bot__id=state_data.bot_id, owner=peer.owner).select_related("bot")
        if bot is None:
            return await send_bot_message(peer, "Bot does not exist (?)")

        async with in_transaction():
            info, _ = await BotInfo.get_or_create(user=bot.bot)
            info.version += 1
            info.description = description
            bot.bot.version += 1
            await bot.save(update_fields=["version"])
            await info.save(update_fields=["description", "version"])
            await state.delete()

        return await send_bot_message(peer, __bot_desc_updated, entities=__bot_desc_updated_entities)

    if state.state is BotFatherState.EDITBOT_WAIT_PHOTO:
        if not message.media or message.media.type is not MediaType.PHOTO:
            return await send_bot_message(peer, __bot_photo_invalid)

        state_data = BotfatherStateEditbot.deserialize(BytesIO(state.data))
        bot = await Bot.get_or_none(bot__id=state_data.bot_id, owner=peer.owner).select_related("bot")
        if bot is None:
            return await send_bot_message(peer, "Bot does not exist (?)")

        storage = request_ctx.get().storage

        file = message.media.file
        photo = file.clone()
        if not await photo.make_thumbs(storage, profile_photo=True):
            return await send_bot_message(peer, __bot_photo_invalid)

        async with in_transaction():
            bot.bot.version += 1
            await bot.save(update_fields=["version"])
            await photo.save()
            await UserPhoto.filter(user=bot.bot).delete()
            await UserPhoto.create(user=bot.bot, file=photo, current=True)

        await state.delete()

        return await send_bot_message(peer, __bot_photo_updated, entities=__bot_photo_updated_entities)

    if state.state is BotFatherState.EDITBOT_WAIT_PRIVACY:
        parsed = urlparse(message.message)
        if not parsed.netloc or parsed.scheme != "https" or len(message.message) > 240:
            return await send_bot_message(peer, __bot_privacy_invalid)

        state_data = BotfatherStateEditbot.deserialize(BytesIO(state.data))
        bot = await Bot.get_or_none(bot__id=state_data.bot_id, owner=peer.owner).select_related("bot")
        if bot is None:
            return await send_bot_message(peer, "Bot does not exist (?)")

        async with in_transaction():
            info, _ = await BotInfo.get_or_create(user=bot.bot)
            info.version += 1
            info.privacy_policy_url = message.message
            bot.bot.version += 1
            await bot.save(update_fields=["version"])
            await info.save(update_fields=["privacy_policy_url", "version"])
            await state.delete()

        return await send_bot_message(peer, _bot_privacy_updated, entities=_bot_privacy_updated_entities)

    if state.state is BotFatherState.EDITBOT_WAIT_COMMANDS:
        commands = {}

        for command in message.message.split("\n"):
            await sleep(0)
            name, _, description = command.partition(" - ")
            # TODO: validate command name
            if not name or len(name) > 32 or not description or len(description) > 240:
                return await send_bot_message(peer, __bot_commands_invalid, entities=__bot_commands_invalid_entities)
            commands[name] = description

        if not commands:
            return await send_bot_message(peer, __bot_commands_invalid, entities=__bot_commands_invalid_entities)

        state_data = BotfatherStateEditbot.deserialize(BytesIO(state.data))
        bot = await Bot.get_or_none(bot__id=state_data.bot_id, owner=peer.owner).select_related("bot")
        if bot is None:
            return await send_bot_message(peer, "Bot does not exist (?)")

        async with in_transaction():
            await BotCommand.filter(bot=bot.bot).delete()

            await BotCommand.bulk_create([
                BotCommand(bot=bot.bot, name=command_name, description=command_description)
                for command_name, command_description in commands.items()
            ])

            info, _ = await BotInfo.get_or_create(user=bot.bot)
            info.version += 1
            await info.save(update_fields=["version"])
            await state.delete()

        return await send_bot_message(peer, _bot_commands_updated, entities=_bot_commands_updated_entities)
