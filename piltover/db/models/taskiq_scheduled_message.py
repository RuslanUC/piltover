from __future__ import annotations

from io import BytesIO
from uuid import UUID, uuid4

from tortoise import fields, Model

from piltover.db import models
from piltover.db.enums import TaskIqScheduledState
from piltover.tl import primitives, LongVector, Int


class TaskIqScheduledMessage(Model):
    id: UUID = fields.UUIDField(pk=True, default=uuid4)
    state: TaskIqScheduledState = fields.IntEnumField(TaskIqScheduledState, default=TaskIqScheduledState.SCHEDULED)
    scheduled_time: int = fields.BigIntField(index=True)
    state_updated_at: int = fields.BigIntField(index=True)
    message: models.MessageRef = fields.OneToOneField("models.MessageRef")
    mentioned_users: bytes | None = fields.BinaryField(null=True)
    opposite: bool = fields.BooleanField()

    message_id: int

    @property
    def mentioned_users_set(self) -> set[int]:
        if not self.mentioned_users:
            return set()

        stream = BytesIO(primitives.VECTOR + Int.write(len(self.mentioned_users) // 8) + self.mentioned_users)
        return set(LongVector.read(stream))
