from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from piltover import tl


def downgrade_offset_for_133(obj: tl.types._root._FileHashDowngradable) -> int:
    return obj.offset
