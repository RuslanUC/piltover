from datetime import datetime, UTC

from piltover.db.enums import BotFatherState
from piltover.db.models import Peer, Message, BotFatherUserState

__text = """
Alright, a new bot. How are we going to call it? Please choose a name for your bot.
"""


async def botfather_newbot_command(peer: Peer, _: Message) -> Message | None:
    await BotFatherUserState.update_or_create(user=peer.owner, defaults={
        "state": BotFatherState.NEWBOT_WAIT_NAME,
        "data": None,
        "last_access": datetime.now(UTC),
    })

    messages = await Message.create_for_peer(peer, None, None, peer.user, False, message=__text)
    return messages[peer]
