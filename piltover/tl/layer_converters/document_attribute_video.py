from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from piltover import tl


def downgrade_duration_for_133(obj: tl.types._root._DocumentAttributeVideoDowngradable) -> int:
    return int(obj.duration)
