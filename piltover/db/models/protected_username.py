from __future__ import annotations

from datetime import datetime

from tortoise import fields, Model

from piltover.db import models


class ProtectedUsername(Model):
    id: int = fields.BigIntField(primary_key=True)
    username: str = fields.CharField(max_length=64, unique=True)
    user: models.User | None = fields.ForeignKeyField("models.User", null=True, default=None)
    channel: models.Channel | None = fields.ForeignKeyField("models.Channel", null=True, default=None)
    removed_at: datetime = fields.DatetimeField(auto_now_add=True)

    user_id: int | None
    channel_id: int | None
