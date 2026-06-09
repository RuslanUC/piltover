from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from piltover import tl


def downgrade_title_for_158(obj: tl.types.chatlists._ChatlistInviteDowngradable) -> str:
    return obj.title.text
