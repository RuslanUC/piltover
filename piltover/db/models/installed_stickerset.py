from __future__ import annotations

from datetime import datetime

from tortoise import Model, fields

from piltover.db import models


class InstalledStickerset(Model):
    id: int = fields.BigIntField(pk=True)
    set: models.Stickerset = fields.ForeignKeyField("models.Stickerset")
    user: models.User = fields.ForeignKeyField("models.User")
    installed_at: datetime = fields.DatetimeField(auto_now_add=True)
    archived: bool = fields.BooleanField(default=False)
    pos: int = fields.IntField(default=0)

    set_id: int
    user_id: int

    class Meta:
        unique_together = (
            ("set", "user"),
        )
