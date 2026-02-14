from io import BytesIO

from piltover.app.bot_handlers.botfather.text_handler import _bot_privacy_updated, _bot_privacy_updated_entities, \
    _bot_commands_updated, _bot_commands_updated_entities
from piltover.app.bot_handlers.botfather.utils import send_bot_message
from piltover.db.enums import BotFatherState
from piltover.db.models import Peer, BotFatherUserState, Bot, BotInfo, BotCommand, MessageRef
from piltover.tl.types.internal_botfather import BotfatherStateEditbot

__text_no_command = "Unrecognized command. Say what?"


async def botfather_empty_command(peer: Peer, _: MessageRef) -> MessageRef | None:
    state = await BotFatherUserState.get_or_none(user=peer.owner)
    if state is None:
        return await send_bot_message(peer, __text_no_command)

    if state.state is BotFatherState.EDITBOT_WAIT_PRIVACY:
        state_data = BotfatherStateEditbot.deserialize(BytesIO(state.data))
        bot = await Bot.get_or_none(bot_id=state_data.bot_id, owner=peer.owner).select_related("bot")
        if bot is None:
            return await send_bot_message(peer, "Bot does not exist (?)")

        await BotInfo.update_or_create(user=bot.bot, defaults={"privacy_policy_url": None})
        await state.delete()

        return await send_bot_message(peer, _bot_privacy_updated, entities=_bot_privacy_updated_entities)
    elif state.state is BotFatherState.EDITBOT_WAIT_COMMANDS:
        state_data = BotfatherStateEditbot.deserialize(BytesIO(state.data))
        await BotCommand.filter(bot_id=state_data.bot_id).delete()

        bot = await Bot.get_or_none(bot_id=state_data.bot_id, owner=peer.owner).select_related("bot")
        if bot is None:
            return await send_bot_message(peer, "Bot does not exist (?)")

        info, _ = await BotInfo.get_or_create(user=bot.bot)
        info.version += 1
        await info.save(update_fields=["version"])

        await state.delete()
        return await send_bot_message(peer, _bot_commands_updated, entities=_bot_commands_updated_entities)

    return await send_bot_message(peer, __text_no_command)
