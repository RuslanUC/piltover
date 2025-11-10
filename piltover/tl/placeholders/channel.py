from __future__ import annotations

from typing import TYPE_CHECKING

from piltover.context import serialization_ctx

if TYPE_CHECKING:
    from piltover.tl import types


def channel_fill_access_hash_calc(obj: types.ChannelForbidden | types.Channel) -> int:
    ctx = serialization_ctx.get()
    if ctx is None:
        return obj.access_hash

    from piltover.db.models import Channel
    return Channel.make_access_hash(ctx.user_id, ctx.auth_id, obj.id)


def input_channel_fill_access_hash_calc(obj: types.InputChannel) -> int:
    ctx = serialization_ctx.get()
    if ctx is None:
        return obj.access_hash

    from piltover.db.models import Channel
    return Channel.make_access_hash(ctx.user_id, ctx.auth_id, obj.channel_id)
