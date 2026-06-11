from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from piltover import tl
    from piltover.tl.serialization_context import SerializationContext


def get_alt_document_fallback_for_160(obj: tl.types.MessageMediaDocument, _: SerializationContext) -> tl.base.Document | None:
    return obj.alt_documents[0] if obj.alt_documents else None
