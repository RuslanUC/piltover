from __future__ import annotations

from tortoise import Model, fields

from piltover.db import models


# TODO: make MessageMention model instead because UnreadMention will be deleted once read
#  and message.mentioned will be set to False even if user is mentioned
class UnreadMention(Model):
    id: int = fields.BigIntField(pk=True)
    peer: models.Peer = fields.ForeignKeyField("models.Peer")
    message: models.Message = fields.ForeignKeyField("models.Message")

    class Meta:
        unique_together = (
            ("peer", "message"),
        )
