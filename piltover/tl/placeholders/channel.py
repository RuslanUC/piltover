from __future__ import annotations

import hashlib
import hmac

from piltover.app_config import AppConfig
from piltover.context import serialization_ctx
from piltover.tl import types
from piltover.tl.primitives import Long


def channel_fill_access_hash_calc(obj: types.ChannelForbidden | types.Channel) -> int:
    ctx = serialization_ctx.get()
    if ctx is None:
        return obj.access_hash

    to_sign = types.internal_access.AccessHashPayloadChannel(
        this_user_id=ctx.user_id, channel_id=obj.id, auth_id=ctx.auth_id,
    ).write()
    digest = hmac.new(AppConfig.HMAC_KEY, to_sign, hashlib.sha256).digest()

    return Long.read_bytes(digest[-8:])


def input_channel_fill_access_hash_calc(obj: types.InputChannel) -> int:
    ctx = serialization_ctx.get()
    if ctx is None:
        return obj.access_hash

    to_sign = types.internal_access.AccessHashPayloadChannel(
        this_user_id=ctx.user_id, channel_id=obj.channel_id, auth_id=ctx.auth_id,
    ).write()
    digest = hmac.new(AppConfig.HMAC_KEY, to_sign, hashlib.sha256).digest()

    return Long.read_bytes(digest[-8:])
