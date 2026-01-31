from __future__ import annotations

from uuid import UUID, uuid4

from tortoise import fields, Model

from piltover.db import models


class TaskIqScheduledDeleteMessage(Model):
    id: UUID = fields.UUIDField(pk=True, default=uuid4)
    scheduled_for: int = fields.BigIntField(index=True)
    start_processing: int | None = fields.BigIntField(null=True, default=None)
    message: models.MessageContent = fields.OneToOneField("models.MessageContent")

    message_id: int
