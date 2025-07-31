from __future__ import annotations

from datetime import datetime
from os import urandom

from tortoise import Model, fields

from piltover.db import models
from piltover.tl import Long


class InstalledStickerset(Model):
    id: int = fields.BigIntField(pk=True)
    set: models.Stickerset = fields.ForeignKeyField("models.Stickerset")
    user: models.User = fields.ForeignKeyField("models.User")
    installed_at: datetime | None = fields.DatetimeField(null=True, default=None)

    set_id: int
    user_id: int
