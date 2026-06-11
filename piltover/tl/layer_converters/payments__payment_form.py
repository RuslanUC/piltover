from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from piltover import tl
    from piltover.tl.serialization_context import SerializationContext


def downgrade_saved_credentials_for_133(obj: tl.types.payments.PaymentForm, _: SerializationContext) -> tl.types.PaymentSavedCredentialsCard | None:
    if not obj.saved_credentials:
        return None
    return obj.saved_credentials[0]
