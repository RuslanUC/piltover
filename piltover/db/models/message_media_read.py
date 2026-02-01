from __future__ import annotations

from tortoise import Model, fields

from piltover.db import models
from piltover.db.models.message import NullableFK


class MessageMediaRead(Model):
    id: int = fields.BigIntField(pk=True)
    user: models.User = fields.ForeignKeyField("models.User")
    message: models.MessageRef = fields.ForeignKeyField("models.MessageRef")

    user_id: int
    message_id: int

    class Meta:
        unique_together = (
            ("user", "message"),
        )
