from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from tortoise import fields, Model

from piltover.db import models
from piltover.db.enums import TaskIqScheduledState


class TaskIqScheduledDeleteUser(Model):
    id: UUID = fields.UUIDField(pk=True, default=uuid4)
    state: TaskIqScheduledState = fields.IntEnumField(TaskIqScheduledState, default=TaskIqScheduledState.SCHEDULED)
    scheduled_time: datetime = fields.DatetimeField(index=True)
    state_updated_at: int = fields.BigIntField(index=True)
    user: models.User = fields.OneToOneField("models.User")

    user_id: int
