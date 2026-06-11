from __future__ import annotations
from typing import TYPE_CHECKING
from piltover import tl

if TYPE_CHECKING:
    from piltover.tl.serialization_context import SerializationContext


def downgrade_sender_id_for_196(obj: tl.types.StarGiftAttributeOriginalDetails, _: SerializationContext) -> int | None:
    if not isinstance(obj.sender_id, tl.types.PeerUser):
        return None
    return obj.sender_id.user_id


def downgrade_recipient_id_for_196(obj: tl.types.StarGiftAttributeOriginalDetails, _: SerializationContext) -> int:
    if not isinstance(obj.recipient_id, tl.types.PeerUser):
        return 0
    return obj.recipient_id.user_id
