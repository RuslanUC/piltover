from __future__ import annotations

from datetime import datetime, UTC

from tortoise import Model, fields

from piltover.db import models
from piltover.db.enums import StickersBotState


class StickersBotUserState(Model):
    id: int = fields.BigIntField(pk=True)
    user: models.User = fields.OneToOneField("models.User")
    state: StickersBotState = fields.IntEnumField(StickersBotState)
    data: bytes | None = fields.BinaryField(null=True, default=None)
    last_access: datetime = fields.DatetimeField(auto_now_add=True)

    async def update_state(self, state: StickersBotState, data: bytes | None) -> None:
        update_fields = ["state", "last_access"]
        self.state = state
        if data is not None:
            self.data = data
            update_fields.append("data")
        self.last_access = datetime.now(UTC)

        await self.save(update_fields=update_fields)
