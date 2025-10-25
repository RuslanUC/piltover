from __future__ import annotations

from tortoise import Model, fields

from piltover.db import models


class AvailableChannelReaction(Model):
    id: int = fields.BigIntField(pk=True)
    channel: models.Channel = fields.ForeignKeyField("models.Channel")
    reaction: models.Reaction = fields.ForeignKeyField("models.Reaction")

    class Meta:
        unique_together = (
            ("channel", "reaction"),
        )
