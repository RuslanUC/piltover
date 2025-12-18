from __future__ import annotations

from datetime import datetime

from tortoise import fields, Model

from piltover.db import models
from piltover.db.enums import InlineQueryPeer
from piltover.tl import InlineQueryPeerTypePM, InlineQueryPeerTypeBotPM, InlineQueryPeerTypeSameBotPM, \
    InlineQueryPeerTypeChat, InlineQueryPeerTypeBroadcast, InlineQueryPeerTypeMegagroup


# TODO: store results in another table, not in cached_data
class InlineQuery(Model):
    id: int = fields.BigIntField(pk=True)
    user: models.User = fields.ForeignKeyField("models.User", related_name="inline_user")
    bot: models.User = fields.ForeignKeyField("models.User", related_name="inline_bot")
    created_at: datetime = fields.DatetimeField(auto_now_add=True)
    # TODO: add index for query and offset?
    query: str = fields.CharField(max_length=128)
    offset: str | None = fields.CharField(max_length=64, null=True, default=None)
    inline_peer: InlineQueryPeer | None = fields.IntEnumField(InlineQueryPeer, null=True, default=None)
    cache_until: datetime = fields.DatetimeField()
    cache_private: bool = fields.BooleanField(default=False)
    cached_data: bytes | None = fields.BinaryField(null=True)

    user_id: int
    bot_id: int
    cache_user_id: int

    INLINE_PEER_TO_TL = {
        InlineQueryPeer.UNKNOWN: None,
        InlineQueryPeer.USER: InlineQueryPeerTypePM(),
        InlineQueryPeer.BOT: InlineQueryPeerTypeBotPM(),
        InlineQueryPeer.SAME_BOT: InlineQueryPeerTypeSameBotPM(),
        InlineQueryPeer.CHAT: InlineQueryPeerTypeChat(),
        InlineQueryPeer.CHANNEL: InlineQueryPeerTypeBroadcast(),
        InlineQueryPeer.SUPERGROUP: InlineQueryPeerTypeMegagroup(),
    }

    INLINE_PEER_FROM_TL = {
        type(None): InlineQueryPeer.UNKNOWN,
        InlineQueryPeerTypePM: InlineQueryPeer.USER,
        InlineQueryPeerTypeBotPM: InlineQueryPeer.BOT,
        InlineQueryPeerTypeSameBotPM: InlineQueryPeer.SAME_BOT,
        InlineQueryPeerTypeChat: InlineQueryPeer.CHAT,
        InlineQueryPeerTypeBroadcast: InlineQueryPeer.CHANNEL,
        InlineQueryPeerTypeMegagroup: InlineQueryPeer.SUPERGROUP,
    }
