from __future__ import annotations

from datetime import datetime

from tortoise import fields, Model

from piltover.db import models


class ReadHistoryChunk(Model):
    id: int = fields.BigIntField(primary_key=True)
    user: models.User = fields.ForeignKeyField("models.User")
    peer: models.Peer = fields.ForeignKeyField("models.Peer")
    read_content_id: int = fields.BigIntField()
    read_at: datetime = fields.DatetimeField(auto_now_add=True)

    class Meta:
        unique_together = (
            ("user_id", "peer_id"),
        )
