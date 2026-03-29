from __future__ import annotations

from tortoise import Model, fields

from piltover.db import models


class MessageUniqueView(Model):
    id: int = fields.BigIntField(primary_key=True)
    message: models.MessageContent = fields.ForeignKeyField("models.MessageContent")
    user: models.User = fields.ForeignKeyField("models.User")

    class Meta:
        unique_together = (
            ("message", "user",),
        )
