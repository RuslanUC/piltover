from __future__ import annotations

from tortoise import Model, fields

from piltover.db import models


class MessageMention(Model):
    id: int = fields.BigIntField(pk=True)
    user: models.User = fields.ForeignKeyField("models.User")
    message: models.MessageContent = fields.ForeignKeyField("models.MessageContent")

    user_id: int
    message_id: int

    class Meta:
        unique_together = (
            ("user", "message"),
        )
