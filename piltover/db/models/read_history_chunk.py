from __future__ import annotations

from datetime import datetime

from tortoise import fields, Model

from piltover.db import models


class ReadHistoryChunk(Model):
    id: int = fields.BigIntField(pk=True)
    peer: models.Peer = fields.ForeignKeyField("models.Peer")
    read_internal_id: int = fields.BigIntField()
    read_at: datetime = fields.DatetimeField(auto_now_add=True)
