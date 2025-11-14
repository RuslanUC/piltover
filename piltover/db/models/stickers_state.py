from __future__ import annotations

from datetime import datetime

from tortoise import Model, fields

from piltover.db import models
from piltover.db.enums import StickersBotState


class StickersBotUserState(Model):
    id: int = fields.BigIntField(pk=True)
    user: models.User = fields.OneToOneField("models.User")
    state: StickersBotState = fields.IntEnumField(StickersBotState)
    data: bytes | None = fields.BinaryField(null=True, default=None)
    last_access: datetime = fields.DatetimeField(auto_now_add=True)
