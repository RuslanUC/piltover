from typing import cast

from piltover.db.enums import BotFatherState, BOTFATHER_STATE_TO_COMMAND_NAME
from piltover.db.models import Peer, Message, BotFatherUserState

__text_no_command = """
No active command to cancel. I wasn't doing anything anyway. Zzzzz...
"""
__text_command_cancel = """
The command {command} has been cancelled. Anything else I can do for you?

Send /help for a list of commands. To learn more about Telegram Bots, see https://core.telegram.org/bots
"""


async def botfather_cancel_command(peer: Peer, _: Message) -> Message | None:
    state = cast(
        BotFatherState | None,
        await BotFatherUserState.filter(user=peer.owner).first().values_list("state", flat=True)
    )
    await BotFatherUserState.filter(user=peer.owner).delete()

    command = BOTFATHER_STATE_TO_COMMAND_NAME[state]
    if command is None:
        text = __text_no_command
    else:
        text = __text_command_cancel.format(command=command)

    messages = await Message.create_for_peer(peer, None, None, peer.user, False, message=text)
    return messages[peer]
