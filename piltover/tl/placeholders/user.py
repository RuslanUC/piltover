from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from piltover.tl import types, SerializationContext


def user_fill_access_hash_calc(obj: types.User, ctx: SerializationContext) -> int | None:
    if ctx.dont_format:
        return obj.access_hash

    from piltover.db.models import User
    return User.make_access_hash(ctx.user_id, ctx.auth_id, obj.id)


def input_user_fill_access_hash_calc(obj: types.InputUser | types.InputPeerUser, ctx: SerializationContext) -> int:
    if ctx.dont_format:
        return obj.access_hash

    from piltover.db.models import User
    return User.make_access_hash(ctx.user_id, ctx.auth_id, obj.user_id)
