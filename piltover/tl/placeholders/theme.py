from __future__ import annotations

from typing import TYPE_CHECKING

from piltover.context import serialization_ctx

if TYPE_CHECKING:
    from piltover.tl import types


def theme_fill_access_hash_calc(obj: types.Theme | types.Theme_133) -> int:
    ctx = serialization_ctx.get()
    if ctx is None:
        return obj.access_hash

    from piltover.db.models import Theme
    return Theme.make_access_hash(ctx.user_id, ctx.auth_id, obj.id)
