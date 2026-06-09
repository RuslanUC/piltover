from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from piltover import tl


def get_background_emoji_id_fallback_for_166(obj: tl.types._root._ChannelDowngradable) -> int | None:
    return None


def downgrade_color_for_166(obj: tl.types._root._ChannelDowngradable) -> int | None:
    if obj.color is None:
        return None
    return obj.color.color
