from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from piltover import tl


def downgrade_peer_types_for_143(obj: tl.types._root._AttachMenuBotDowngradable) -> list[tl.base.AttachMenuPeerType]:
    if obj.peer_types is None:
        return []
    return obj.peer_types
