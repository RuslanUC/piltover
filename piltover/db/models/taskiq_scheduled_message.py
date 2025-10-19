from __future__ import annotations

from uuid import UUID, uuid4

from tortoise import fields, Model

from piltover.db import models


class TaskIqScheduledMessage(Model):
    id: UUID = fields.UUIDField(pk=True, default=uuid4)
    scheduled_time: int = fields.BigIntField(index=True)
    start_processing: int | None = fields.BigIntField(null=True, default=None)
    message: models.Message = fields.OneToOneField("models.Message")
    mentioned_users: bytes | None = fields.BinaryField(null=True)
    opposite: bool = fields.BooleanField()

    message_id: int

