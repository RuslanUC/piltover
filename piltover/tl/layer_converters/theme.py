from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from piltover import tl
    from piltover.tl.serialization_context import SerializationContext


def downgrade_settings_for_133(obj: tl.types.Theme, _: SerializationContext) -> tl.types.ThemeSettings | None:
    if not obj.settings:
        return None
    return obj.settings[0]
