from asyncio import sleep
from io import BytesIO
from urllib.parse import urlparse

from tortoise.expressions import F
from tortoise.transactions import in_transaction

from piltover.app.bot_handlers.botfather.utils import send_bot_message
from piltover.app.bot_handlers.interaction_handler import BotInteractionHandler
from piltover.app.utils.formatable_text_with_entities import FormatableTextWithEntities
from piltover.app.utils.utils import is_username_valid, BOT_COMMAND_NAME_REGEX
from piltover.context import request_ctx
from piltover.db.enums import BotFatherState, MediaType, PeerType
from piltover.db.models import Peer, BotFatherUserState, Username, User, Bot, BotInfo, UserPhoto, BotCommand, State, \
    MessageRef
from piltover.tl.types.internal_botfather import BotfatherStateNewbot, BotfatherStateEditbot

_bot_name_invalid = "Sorry, this isn't a proper name for a bot."
_bot_wait_username = (
    "Good. Now let's choose a username for your bot. "
    "It must end in `bot`. Like this, for example: TetrisBot or tetris_bot."
)
_bot_username_invalid = "Sorry, this username is invalid."
_bot_username_ends_bot = "Sorry, the username must end in `bot`. E.g. Tetris_bot or Tetrisbot."
_bot_username_taken = "Sorry, this username is already taken. Please try something different."
_bot_created = FormatableTextWithEntities("""
Done! Congratulations on your new bot. You will find it at <a>t.me/{username}</a>. You can now add a description, about section and profile picture for your bot, see <c>/help</c> for a list of commands. By the way, when you've finished creating your cool bot, ping our Bot Support if you want a better username for it. Just make sure the bot is fully operational before you do this.

Use this token to access the HTTP API:
`{token}`
Keep your token secure and store it safely, it can be used by anyone to control your bot.

For a description of the Bot API, see this page: <a>https://core.telegram.org/bots/api</a>
""".strip())
_bot_name_updated, _bot_name_updated_entities = FormatableTextWithEntities(
    "Success! Name updated. <c>/help</c>",
).format()
_bot_about_invalid = "Sorry, the about info you provided is invalid. It must not exceed 120 characters."
_bot_about_updated, _bot_about_updated_entities = FormatableTextWithEntities(
    "Success! About section updated. <c>/help</c>",
).format()
_bot_desc_invalid = (
    "Sorry the description you provided is invalid. "
    "A description may not exceed 120 characters (line breaks included)."
)
_bot_desc_updated, _bot_desc_updated_entities = FormatableTextWithEntities(
    "Success! Description updated. You will be able to see the changes within a few minutes. <c>/help</c>",
).format()
_bot_photo_invalid = "Please send me the picture as a 'Photo', not as a 'File'."
_bot_photo_updated, _bot_photo_updated_entities = FormatableTextWithEntities(
    "Success! Profile photo updated. <c>/help</c>",
).format()
_bot_privacy_invalid = "Please send me a valid URL."
_bot_privacy_updated, _bot_privacy_updated_entities = FormatableTextWithEntities(
    "Success! Privacy policy updated. <c>/help</c>",
).format()
_bot_commands_updated, _bot_commands_updated_entities = FormatableTextWithEntities(
    "Success! Command list updated. <c>/help</c>",
).format()
_bot_commands_invalid, _bot_commands_invalid_entities = FormatableTextWithEntities("""
Sorry, the list of commands is invalid. Please use this format:

command1 - Description
command2 - Another description

Send <c>/empty</c> to keep the list empty.
""".strip()).format()


class Text(BotInteractionHandler[BotFatherState, BotFatherUserState]):
    def __init__(self) -> None:
        super().__init__(BotFatherUserState)
        (
            self.text()

            .when(state=BotFatherState.NEWBOT_WAIT_NAME).do(self._handler_newbot_name)
            .when(state=BotFatherState.NEWBOT_WAIT_USERNAME).do(self._handler_newbot_username)
            .when(state=BotFatherState.EDITBOT_WAIT_NAME).do(self._handler_editbot_name)
            .when(state=BotFatherState.EDITBOT_WAIT_ABOUT).do(self._handler_editbot_about)
            .when(state=BotFatherState.EDITBOT_WAIT_DESCRIPTION).do(self._handler_editbot_description)
            .when(state=BotFatherState.EDITBOT_WAIT_NAME).do(self._handler_editbot_name)
            .when(state=BotFatherState.EDITBOT_WAIT_PHOTO).do(self._handler_editbot_photo)
            .when(state=BotFatherState.EDITBOT_WAIT_PRIVACY).do(self._handler_editbot_privacy)
            .when(state=BotFatherState.EDITBOT_WAIT_COMMANDS).do(self._handler_editbot_commands)

            .register()
        )

    @staticmethod
    async def _handler_newbot_name(peer: Peer, message: MessageRef, state: BotFatherUserState) -> MessageRef:
        first_name = message.content.message
        if len(first_name) > 64:
            return await send_bot_message(peer, _bot_name_invalid)

        await state.update_state(BotFatherState.NEWBOT_WAIT_USERNAME, BotfatherStateNewbot(name=first_name).serialize())
        return await send_bot_message(peer, _bot_wait_username)

    @staticmethod
    async def _handler_newbot_username(peer: Peer, message: MessageRef, state: BotFatherUserState) -> MessageRef:
        username = message.content.message
        if not is_username_valid(username):
            return await send_bot_message(peer, _bot_username_invalid)
        if not username.endswith("bot"):
            return await send_bot_message(peer, _bot_username_ends_bot)
        if await Username.filter(username=username).exists():
            return await send_bot_message(peer, _bot_username_taken)

        state_data = BotfatherStateNewbot.deserialize(BytesIO(state.data))

        async with in_transaction():
            bot_user = await User.create(phone_number=None, first_name=state_data.name, bot=True)
            await State.create(user=bot_user)
            await Peer.create(owner=bot_user, type=PeerType.SELF, user=bot_user)
            await Username.create(user=bot_user, username=username)
            bot = await Bot.create(owner=peer.owner, bot=bot_user)
            await BotInfo.create(user=bot_user)
            await state.delete()

        text, entities = _bot_created.format(username=username, token=f"{bot_user.id}:{bot.token_nonce}")
        return await send_bot_message(peer, text, entities=entities)

    @staticmethod
    async def _handler_editbot_name(peer: Peer, message: MessageRef, state: BotFatherUserState) -> MessageRef:
        first_name = message.content.message
        if len(first_name) > 64:
            return await send_bot_message(peer, _bot_name_invalid)

        state_data = BotfatherStateEditbot.deserialize(BytesIO(state.data))
        bot = await Bot.get_or_none(bot_id=state_data.bot_id, owner=peer.owner).only("bot_id")
        if bot is None:
            return await send_bot_message(peer, "Bot does not exist (?)")

        async with in_transaction():
            await User.filter(id=bot.bot_id).update(first_name=first_name, version=F("version") + 1)
            await state.delete()

        return await send_bot_message(peer, _bot_name_updated, entities=_bot_name_updated_entities)

    @staticmethod
    async def _handler_editbot_about(peer: Peer, message: MessageRef, state: BotFatherUserState) -> MessageRef:
        about = message.content.message
        if len(about) > 120:
            return await send_bot_message(peer, _bot_about_invalid)

        state_data = BotfatherStateEditbot.deserialize(BytesIO(state.data))
        bot = await Bot.get_or_none(bot_id=state_data.bot_id, owner=peer.owner).only("bot_id")
        if bot is None:
            return await send_bot_message(peer, "Bot does not exist (?)")

        async with in_transaction():
            await User.filter(id=bot.bot_id).update(about=about, version=F("version") + 1)
            await state.delete()

        return await send_bot_message(peer, _bot_about_updated, entities=_bot_about_updated_entities)

    @staticmethod
    async def _handler_editbot_description(peer: Peer, message: MessageRef, state: BotFatherUserState) -> MessageRef:
        description = message.content.message
        if len(description) > 120:
            return await send_bot_message(peer, _bot_desc_invalid)

        state_data = BotfatherStateEditbot.deserialize(BytesIO(state.data))
        bot = await Bot.get_or_none(bot_id=state_data.bot_id, owner=peer.owner).only("bot_id")
        if bot is None:
            return await send_bot_message(peer, "Bot does not exist (?)")

        async with in_transaction():
            await User.filter(id=bot.bot_id).update(version=F("version") + 1)
            await BotInfo.filter(user_id=bot.bot_id).update(description=description, version=F("version") + 1)
            await state.delete()

        return await send_bot_message(peer, _bot_desc_updated, entities=_bot_desc_updated_entities)

    @staticmethod
    async def _handler_editbot_photo(peer: Peer, message: MessageRef, state: BotFatherUserState) -> MessageRef:
        if not message.content.media or message.content.media.type is not MediaType.PHOTO:
            return await send_bot_message(peer, _bot_photo_invalid)

        state_data = BotfatherStateEditbot.deserialize(BytesIO(state.data))
        bot = await Bot.get_or_none(bot_id=state_data.bot_id, owner=peer.owner).only("bot_id")
        if bot is None:
            return await send_bot_message(peer, "Bot does not exist (?)")

        storage = request_ctx.get().storage

        file = message.content.media.file
        photo = file.clone()
        if not await photo.make_thumbs(storage, profile_photo=True):
            return await send_bot_message(peer, _bot_photo_invalid)

        async with in_transaction():
            await photo.save()
            await UserPhoto.filter(user_id=bot.bot_id).delete()
            await UserPhoto.create(user_id=bot.bot_id, file=photo, current=True)
            await User.filter(id=bot.bot_id).update(version=F("version") + 1)

        await state.delete()

        return await send_bot_message(peer, _bot_photo_updated, entities=_bot_photo_updated_entities)

    @staticmethod
    async def _handler_editbot_privacy(peer: Peer, message: MessageRef, state: BotFatherUserState) -> MessageRef:
        parsed = urlparse(message.content.message)
        if not parsed.netloc or parsed.scheme != "https" or len(message.content.message) > 240:
            return await send_bot_message(peer, _bot_privacy_invalid)

        state_data = BotfatherStateEditbot.deserialize(BytesIO(state.data))
        bot = await Bot.get_or_none(bot_id=state_data.bot_id, owner=peer.owner).only("bot_id")
        if bot is None:
            return await send_bot_message(peer, "Bot does not exist (?)")

        async with in_transaction():
            await User.filter(id=bot.bot_id).update(version=F("version") + 1)
            await BotInfo.filter(user_id=bot.bot_id).update(
                privacy_policy_url=message.content.message, version=F("version") + 1,
            )
            await state.delete()

        return await send_bot_message(peer, _bot_privacy_updated, entities=_bot_privacy_updated_entities)

    @staticmethod
    async def _handler_editbot_commands(peer: Peer, message: MessageRef, state: BotFatherUserState) -> MessageRef:
        commands = {}

        for command in message.content.message.split("\n"):
            await sleep(0)
            name, _, description = command.partition(" - ")
            if not name \
                    or len(name) > 32 \
                    or not description \
                    or len(description) > 240 \
                    or not BOT_COMMAND_NAME_REGEX.fullmatch(name):
                return await send_bot_message(peer, _bot_commands_invalid, entities=_bot_commands_invalid_entities)
            commands[name] = description

        if not commands:
            return await send_bot_message(peer, _bot_commands_invalid, entities=_bot_commands_invalid_entities)

        state_data = BotfatherStateEditbot.deserialize(BytesIO(state.data))
        bot = await Bot.get_or_none(bot_id=state_data.bot_id, owner=peer.owner).only("bot_id")
        if bot is None:
            return await send_bot_message(peer, "Bot does not exist (?)")

        async with in_transaction():
            await BotCommand.filter(bot_id=bot.bot_id).delete()

            await BotCommand.bulk_create([
                BotCommand(bot_id=bot.bot_id, name=command_name, description=command_description)
                for command_name, command_description in commands.items()
            ])

            await User.filter(id=bot.bot_id).update(version=F("version") + 1)
            await BotInfo.filter(user_id=bot.bot_id).update(version=F("version") + 1)
            await state.delete()

        return await send_bot_message(peer, _bot_commands_updated, entities=_bot_commands_updated_entities)
