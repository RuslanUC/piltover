from __future__ import annotations

from datetime import datetime

from tortoise import Model, fields

from piltover.db import models


class SlowmodeLastMessage(Model):
    id: int = fields.BigIntField(pk=True)
    channel: models.Channel = fields.ForeignKeyField("models.Channel")
    user: models.User = fields.ForeignKeyField("models.User")
    last_message: datetime = fields.DatetimeField()

    class Meta:
        unique_together = (
            ("channel", "user"),
        )
