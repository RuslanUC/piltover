from __future__ import annotations

from datetime import datetime, UTC
from enum import IntEnum, Enum, auto
from typing import TypeVar

from tortoise import Model, fields

from piltover.db import models

StateEnumT = TypeVar("StateEnumT", bound=IntEnum)


class StateMissing(Enum):
    STATE_MISSING = auto()


STATE_MISSING = StateMissing.STATE_MISSING


class BotUserStateBase(Model):
    id: int = fields.BigIntField(pk=True)
    user: models.User = fields.OneToOneField("models.User")
    state: StateEnumT
    data: bytes | None = fields.BinaryField(null=True, default=None)
    last_access: datetime = fields.DatetimeField(auto_now_add=True)

    class Meta:
        abstract = True

    async def update_state(self, state: StateEnumT, data: bytes | None) -> None:
        update_fields = ["state", "last_access"]
        self.state = state
        if data is not None:
            self.data = data
            update_fields.append("data")
        self.last_access = datetime.now(UTC)

        await self.save(update_fields=update_fields)

    @classmethod
    async def set_state(cls, user: models.User, state: StateEnumT, data: bytes | None | StateMissing) -> None:
        defaults = {
            "state": state,
            "last_access": datetime.now(UTC),
        }
        if data is not STATE_MISSING:
            defaults["data"] = data

        await cls.update_or_create(user=user, defaults=defaults)
