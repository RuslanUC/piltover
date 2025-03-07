from __future__ import annotations

from datetime import datetime

from tortoise import Model, fields

from piltover.db import models


class PollVote(Model):
    id: int = fields.BigIntField(pk=True)
    user: models.User = fields.ForeignKeyField("models.User")
    answer: models.PollAnswer = fields.ForeignKeyField("models.PollAnswer")
    hidden: bool = fields.BooleanField(default=False)
    voted_at: datetime = fields.DatetimeField(auto_now_add=True)

    class Meta:
        unique_together = (
            ("user", "answer",),
        )
