from __future__ import annotations

from datetime import datetime

from tortoise import Model, fields

from piltover.db import models
from piltover.db.enums import BotFatherState


class BotFatherUserState(Model):
    id: int = fields.BigIntField(pk=True)
    user: models.User = fields.OneToOneField("models.User")
    state: BotFatherState = fields.IntEnumField(BotFatherState)
    data: bytes | None = fields.BinaryField(null=True, default=None)
    last_access: datetime = fields.DatetimeField(auto_now_add=True)
