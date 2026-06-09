from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from piltover import tl


def downgrade_title_for_133(obj: tl.types._root._DialogFilterDowngradable) -> str:
    return obj.title.text
