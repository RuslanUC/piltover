from __future__ import annotations

from datetime import datetime

from tortoise import fields, Model

from piltover.db import models


class CallbackQuery(Model):
    id: int = fields.BigIntField(pk=True)
    user: models.User = fields.ForeignKeyField("models.User")
    message: models.Message = fields.ForeignKeyField("models.Message")
    created_at: datetime = fields.DatetimeField(auto_now_add=True)
    data: bytes = fields.BinaryField()
    response: bool = fields.BooleanField(default=False)
    response_alert: bool = fields.BooleanField(default=False)
    response_message: str | None = fields.CharField(max_length=240, null=True, default=None)
    response_url: str | None = fields.TextField(null=True, default=None)
    cache_time: int = fields.IntField(default=0)

    user_id: int
    message_id: int
