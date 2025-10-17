from __future__ import annotations
from tortoise import fields, Model

from piltover.db import models


class Username(Model):
    id: int = fields.BigIntField(pk=True)
    username: str = fields.CharField(max_length=64, unique=True)
    user: models.User | None = fields.OneToOneField("models.User", null=True, default=None)
    channel: models.Channel | None = fields.OneToOneField("models.Channel", null=True, default=None)
