from types import NoneType

from piltover.app.bot_handlers.interaction_handler import BotInteractionHandler
from piltover.db.models import Peer, MessageRef


async def send_bot_message(peer: Peer, text: str, entities: list[dict[str, str | int]] | None = None) -> MessageRef:
    messages = await MessageRef.create_for_peer(peer, peer.user, opposite=False, message=text, entities=entities)
    return messages[peer]


class PingTestBotBotInteractionHandler(BotInteractionHandler[NoneType, NoneType]):
    def __init__(self) -> None:
        super().__init__(None)
        self.command("ping").set_send_message_func(send_bot_message).do().respond("Pong").ok().register()
