from __future__ import annotations

from datetime import datetime, UTC
from enum import Enum, auto

from tortoise import Model, fields

from piltover.db import models
from piltover.db.enums import BotFatherState


class _StateMissing(Enum):
    STATE_MISSING = auto()


_STATE_MISSING = _StateMissing.STATE_MISSING


class BotFatherUserState(Model):
    id: int = fields.BigIntField(pk=True)
    user: models.User = fields.OneToOneField("models.User")
    state: BotFatherState = fields.IntEnumField(BotFatherState)
    data: bytes | None = fields.BinaryField(null=True, default=None)
    last_access: datetime = fields.DatetimeField(auto_now_add=True)

    async def update_state(self, state: BotFatherState, data: bytes | None) -> None:
        update_fields = ["state", "last_access"]
        self.state = state
        if data is not None:
            self.data = data
            update_fields.append("data")
        self.last_access = datetime.now(UTC)

        await self.save(update_fields=update_fields)

    @classmethod
    async def set_state(cls, user: models.User, state: BotFatherState, data: bytes | None | _StateMissing) -> None:
        defaults = {
            "state": state,
            "last_access": datetime.now(UTC),
        }
        if data is not _STATE_MISSING:
            defaults["data"] = data

        await cls.update_or_create(user=user, defaults=defaults)
