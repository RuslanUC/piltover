from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from piltover import tl
    from piltover.tl.serialization_context import SerializationContext


def downgrade_query_id_for_140(obj: tl.types._root.WebViewResultUrl, ctx: SerializationContext) -> int:
    if obj.query_id is not None:
        return obj.query_id
    return 0
