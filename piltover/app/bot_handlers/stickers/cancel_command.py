from typing import cast

from piltover.db.enums import StickersBotState, STICKERS_STATE_TO_COMMAND_NAME
from piltover.db.models import Peer, Message
from piltover.db.models.stickers_state import StickersBotUserState

__text_no_command = """
No active command to cancel. I wasn't doing anything anyway. Zzzzz...
""".strip()
__text_command_cancel = """
The command {command} has been cancelled. Anything else I can do for you?

Send /help for a list of commands.
""".strip()


async def stickers_cancel_command(peer: Peer, _: Message) -> Message | None:
    state = cast(
        StickersBotState | None,
        await StickersBotUserState.filter(user=peer.owner).first().values_list("state", flat=True)
    )
    await StickersBotUserState.filter(user=peer.owner).delete()

    command = STICKERS_STATE_TO_COMMAND_NAME[state]
    if command is None:
        text = __text_no_command
    else:
        text = __text_command_cancel.format(command=command)

    messages = await Message.create_for_peer(peer, None, None, peer.user, False, message=text)
    return messages[peer]
