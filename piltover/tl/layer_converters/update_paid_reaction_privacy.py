from __future__ import annotations
from typing import TYPE_CHECKING
from piltover import tl

if TYPE_CHECKING:
    from piltover.tl.serialization_context import SerializationContext


def downgrade_private_for_187(obj: tl.types.UpdatePaidReactionPrivacy, _: SerializationContext) -> bool:
    return isinstance(obj.private, tl.types.PaidReactionPrivacyAnonymous)
