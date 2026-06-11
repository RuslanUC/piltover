from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from piltover import tl
    from piltover.tl.serialization_context import SerializationContext


def get_username_fallback_for_133(obj: tl.types.UpdateUserName, _: SerializationContext) -> str:
    active = [username.username for username in obj.usernames if username.active]
    return active[0] if active else ""
