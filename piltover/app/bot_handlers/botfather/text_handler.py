from datetime import datetime, UTC
from io import BytesIO

from tortoise.transactions import in_transaction

from piltover.app.utils.utils import is_username_valid
from piltover.db.enums import BotFatherState
from piltover.db.models import Peer, Message, BotFatherUserState, Username, User, Bot
from piltover.tl.types.internal_botfather import BotfatherStateNewbot

__bot_name_invalid = "Sorry, this isn't a proper name for a bot."
__bot_wait_username = ("Good. Now let's choose a username for your bot. It must end in `bot`. "
                       "Like this, for example: TetrisBot or tetris_bot.")
__bot_username_invalid = "Sorry, this username is invalid."
__bot_username_ends_bot = "Sorry, the username must end in `bot`. E.g. Tetris_bot or Tetrisbot."
__bot_username_taken = "Sorry, this username is already taken. Please try something different."
__bot_created = """
Done! Congratulations on your new bot. You will find it at t.me/{username}. You can now add a description, about section and profile picture for your bot, see /help for a list of commands. By the way, when you've finished creating your cool bot, ping our Bot Support if you want a better username for it. Just make sure the bot is fully operational before you do this.

Use this token to access the HTTP API:
{token}
Keep your token secure and store it safely, it can be used by anyone to control your bot.

For a description of the Bot API, see this page: https://core.telegram.org/bots/api
"""


async def botfather_text_message_handler(peer: Peer, message: Message) -> Message | None:
    state = await BotFatherUserState.get_or_none(user=peer.owner)
    if state is None:
        return None

    if state.state is BotFatherState.NEWBOT_WAIT_NAME:
        first_name = message.message
        if len(first_name) > 64:
            messages = await Message.create_for_peer(peer, None, None, peer.user, False, message=__bot_name_invalid)
            return messages[peer]

        state.state = BotFatherState.NEWBOT_WAIT_USERNAME
        state.data = BotfatherStateNewbot(name=first_name).serialize()
        state.last_access = datetime.now(UTC)
        await state.save(update_fields=["state", "data", "last_access"])

        messages = await Message.create_for_peer(peer, None, None, peer.user, False, message=__bot_wait_username)
        return messages[peer]
    elif state.state is BotFatherState.NEWBOT_WAIT_USERNAME:
        username = message.message
        if not is_username_valid(username):
            messages = await Message.create_for_peer(
                peer, None, None, peer.user, False, message=__bot_username_invalid,
            )
            return messages[peer]
        if not username.endswith("bot"):
            messages = await Message.create_for_peer(
                peer, None, None, peer.user, False, message=__bot_username_ends_bot,
            )
            return messages[peer]
        if await Username.filter(username=username).exists():
            messages = await Message.create_for_peer(
                peer, None, None, peer.user, False, message=__bot_username_taken,
            )
            return messages[peer]

        state_data = BotfatherStateNewbot.deserialize(BytesIO(state.data))

        async with in_transaction():
            bot_user = await User.create(phone_number=None, first_name=state_data.name, bot=True)
            await Username.create(user=bot_user, username=username)
            bot = await Bot.create(owner=peer.owner, bot=bot_user)

        messages = await Message.create_for_peer(peer, None, None, peer.user, False, message=__bot_created.format(
            username=username, token=f"{bot_user.id}:{bot.token_nonce}"
        ))
        return messages[peer]

    ...  # TODO: process user state (from BotFatherUserState)
