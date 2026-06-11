from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from piltover import tl
    from piltover.tl.serialization_context import SerializationContext


def downgrade_provider_for_133(obj: tl.types.InputMediaInvoice, c_tx: SerializationContext) -> str:
    if obj.provider is not None:
        return obj.provider
    return ""
