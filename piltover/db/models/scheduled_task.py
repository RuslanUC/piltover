from __future__ import annotations

from datetime import datetime

from tortoise import Model, fields

from piltover.db import models
from piltover.db.enums import ScheduledTaskType, ScheduledTaskState


class ScheduledTask(Model):
    id: int = fields.BigIntField(primary_key=True)
    type: ScheduledTaskType = fields.IntEnumField(ScheduledTaskType, description="")
    state: ScheduledTaskState = fields.IntEnumField(ScheduledTaskState, description="")
    scheduled_at: datetime = fields.DateTimeField()
    next_attempt_at: datetime = fields.DateTimeField()
    generation: int = fields.SmallIntField(default=0)
    message: models.MessageRef = fields.ForeignKey("models.MessageRef", null=True, default=None)
    extra_info: bytes | None = fields.BinaryField(null=True, default=None)

    message_id: int | None
