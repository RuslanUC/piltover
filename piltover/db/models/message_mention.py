from __future__ import annotations

from tortoise import Model, fields

from piltover.db import models


class MessageMention(Model):
    id: int = fields.BigIntField(pk=True)
    peer: models.Peer = fields.ForeignKeyField("models.Peer")
    message: models.Message = fields.ForeignKeyField("models.Message")

    peer_id: int
    message_id: int

    class Meta:
        unique_together = (
            ("peer", "message"),
        )
