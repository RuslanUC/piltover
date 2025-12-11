from io import BytesIO

from tortoise.transactions import in_transaction

from piltover.app.bot_handlers.botfather.utils import send_bot_message
from piltover.app.utils.formatable_text_with_entities import FormatableTextWithEntities
from piltover.app.utils.utils import is_username_valid
from piltover.db.enums import BotFatherState
from piltover.db.models import Peer, Message, BotFatherUserState, Username, User, Bot
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

        bot.bot.first_name = first_name
        await bot.bot.save(update_fields=["first_name"])
        await state.delete()

        return await send_bot_message(peer, __bot_name_updated, entities=__bot_name_updated_entities)
