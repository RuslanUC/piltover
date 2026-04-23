from io import BytesIO

from piltover.app.bot_handlers.botfather.text_handler import _bot_privacy_updated, _bot_privacy_updated_entities, \
    _bot_commands_updated, _bot_commands_updated_entities
from piltover.app.bot_handlers.botfather.utils import send_bot_message
from piltover.app.bot_handlers.interaction_handler import BotInteractionHandler
from piltover.db.enums import BotFatherState
from piltover.db.models import Peer, BotFatherUserState, Bot, BotInfo, BotCommand, MessageRef
from piltover.tl.types.internal_botfather import BotfatherStateEditbot

_text_no_command = "Unrecognized command. Say what?"


class Empty(BotInteractionHandler[BotFatherState, BotFatherUserState]):
    def __init__(self) -> None:
        super().__init__(BotFatherUserState)
        (
            self.command("empty").set_send_message_func(send_bot_message)

            .when(state=BotFatherState.EDITBOT_WAIT_PRIVACY).do(self._handler_privacy)
            .when(state=BotFatherState.EDITBOT_WAIT_COMMANDS).do(self._handler_commands)

            .otherwise().respond(_text_no_command).ok()

            .register()
        )

    @staticmethod
    async def _handler_privacy(peer: Peer, _message: MessageRef, state: BotFatherUserState) -> MessageRef:
        state_data = BotfatherStateEditbot.deserialize(BytesIO(state.data))
        bot = await Bot.get_or_none(bot_id=state_data.bot_id, owner=peer.owner)
        if bot is None:
            return await send_bot_message(peer, "Bot does not exist (?)")

        await BotInfo.update_or_create(user_id=bot.bot_id, defaults={"privacy_policy_url": None})
        await state.delete()

        return await send_bot_message(peer, _bot_privacy_updated, entities=_bot_privacy_updated_entities)

    @staticmethod
    async def _handler_commands(peer: Peer, _message: MessageRef, state: BotFatherUserState) -> MessageRef:
        state_data = BotfatherStateEditbot.deserialize(BytesIO(state.data))
        await BotCommand.filter(bot_id=state_data.bot_id).delete()

        bot = await Bot.get_or_none(bot_id=state_data.bot_id, owner=peer.owner)
        if bot is None:
            return await send_bot_message(peer, "Bot does not exist (?)")

        info, _ = await BotInfo.get_or_create(user_id=bot.bot_id)
        info.version += 1
        await info.save(update_fields=["version"])

        await state.delete()
        return await send_bot_message(peer, _bot_commands_updated, entities=_bot_commands_updated_entities)
