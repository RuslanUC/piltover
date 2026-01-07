from __future__ import annotations

from datetime import datetime

from tortoise import Model, fields

from piltover.db import models


class ChannelParticipantBan(Model):
    id: int = fields.BigIntField(pk=True)
    user: models.User = fields.ForeignKeyField("models.User")
    channel: models.Channel = fields.ForeignKeyField("models.Channel")
    until: datetime = fields.DatetimeField()

    class Meta:
        unique_together = (
            ("user", "channel"),
        )
