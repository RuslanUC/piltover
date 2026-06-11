from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from piltover import tl
    from piltover.tl.serialization_context import SerializationContext


def downgrade_domain_for_133(obj: tl.types.MessageActionBotAllowed, _: SerializationContext) -> str:
    if obj.domain is not None:
        return obj.domain
    return ""
