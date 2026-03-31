from time import time
from types import NoneType

from piltover.app.bot_handlers.interaction_handler import BotInteractionHandler
from piltover.app.utils.formatable_text_with_entities import FormatableTextWithEntities
from piltover.app.utils.updates_manager import UpdatesWithDefaults
from piltover.db.models import Peer, MessageRef
from piltover.session import SessionManager
from piltover.tl import UpdateServiceNotification, MessageMediaEmpty, objects

_text_notif_text, _text_notif_entities_dicts = FormatableTextWithEntities(
    "**t**~~e~~__s__**t** **s**`e`__r__~~v~~--i--||c||**e** ||n||--o--~~t~~__i__`f`||i||--c--**a**~~t~~`i`**o**__n__\n" * 100
).format()
_text_notif_entities = []
for entity in _text_notif_entities_dicts:
    tl_id = entity.pop("_")
    _text_notif_entities.append(objects[tl_id](**entity))
    entity["_"] = tl_id


async def send_bot_message(peer: Peer, text: str, entities: list[dict[str, str | int]] | None = None) -> MessageRef:
    messages = await MessageRef.create_for_peer(peer, peer.user, opposite=False, message=text, entities=entities)
    return messages[peer]


class PingTestBotBotInteractionHandler(BotInteractionHandler[NoneType, NoneType]):
    def __init__(self) -> None:
        super().__init__(None)
        self.command("ping").set_send_message_func(send_bot_message).do().respond("Pong").ok().register()
        self.command("test").do(self._handler_test).register()

    @staticmethod
    async def _handler_test(peer: Peer, _message: MessageRef, _state: None) -> MessageRef:
        updates_to_send = UpdatesWithDefaults(
            updates=[
                UpdateServiceNotification(
                    popup=True,
                    inbox_date=int(time()),
                    type_=f"TEST_{int(time()) * 1000}",
                    message=_text_notif_text,
                    media=MessageMediaEmpty(),
                    entities=_text_notif_entities,
                )
            ]
        )
        await SessionManager.send(updates_to_send, peer.owner.id)

        return await send_bot_message(peer, "test")
