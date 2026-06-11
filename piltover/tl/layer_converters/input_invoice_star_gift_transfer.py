from __future__ import annotations
from typing import TYPE_CHECKING
from piltover import tl

if TYPE_CHECKING:
    from piltover.tl.serialization_context import SerializationContext


def get_msg_id_fallback_for_196(obj: tl.types.InputInvoiceStarGiftTransfer, _: SerializationContext) -> int:
    if isinstance(obj.stargift, tl.types.InputSavedStarGiftUser):
        return obj.stargift.msg_id
    return 0


def downgrade_to_id_for_196(obj: tl.types.InputInvoiceStarGiftTransfer, _: SerializationContext) -> tl.base.InputUser:
    if isinstance(obj.to_id, tl.types.InputPeerUser):
        return tl.types.InputUser(user_id=obj.to_id.user_id, access_hash=obj.to_id.access_hash)
    return tl.types.InputUser(user_id=0, access_hash=0)
