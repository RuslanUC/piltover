from __future__ import annotations

from typing import TYPE_CHECKING

from piltover.context import serialization_ctx

if TYPE_CHECKING:
    from piltover.tl import types


def encrypted_chat_fill_access_hash_calc(obj: types.EncryptedChat) -> int:
    ctx = serialization_ctx.get()
    if ctx is None:
        return obj.access_hash

    from piltover.db.models import EncryptedChat
    return EncryptedChat.make_access_hash(ctx.user_id, ctx.auth_id, obj.id)
