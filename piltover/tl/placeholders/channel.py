from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from piltover.tl import types, SerializationContext


def channel_fill_access_hash_calc(obj: types.ChannelForbidden | types.Channel, ctx: SerializationContext) -> int | None:
    if ctx.dont_format:
        return obj.access_hash

    from piltover.db.models import Channel
    return Channel.make_access_hash(ctx.user_id, ctx.auth_id, Channel.norm_id(obj.id))


def input_channel_fill_access_hash_calc(obj: types.InputChannel, ctx: SerializationContext) -> int:
    if ctx.dont_format:
        return obj.access_hash

    from piltover.db.models import Channel
    return Channel.make_access_hash(ctx.user_id, ctx.auth_id, Channel.norm_id(obj.channel_id))
