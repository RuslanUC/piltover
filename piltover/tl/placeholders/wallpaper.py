from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from piltover.tl import types, SerializationContext


def wallpaper_fill_access_hash_calc(obj: types.WallPaper, ctx: SerializationContext) -> int:
    if ctx.dont_format:
        return obj.access_hash

    from piltover.db.models import Wallpaper
    return Wallpaper.make_access_hash(ctx.user_id, ctx.auth_id, obj.id)
