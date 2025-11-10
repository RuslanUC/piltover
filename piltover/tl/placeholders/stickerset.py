from __future__ import annotations

from typing import TYPE_CHECKING

from piltover.context import serialization_ctx

if TYPE_CHECKING:
    from piltover.tl import types


def stickerset_fill_access_hash_calc(obj: types.StickerSet | types.StickerSet_133) -> int:
    ctx = serialization_ctx.get()
    if ctx is None:
        return obj.access_hash

    from piltover.db.models import Stickerset
    return Stickerset.make_access_hash(ctx.user_id, ctx.auth_id, obj.id)
