from __future__ import annotations

from datetime import datetime
from time import mktime

from tortoise import fields

from piltover.db import models
from piltover.db.models._utils import Model
from piltover.tl_new import DraftMessage


class MessageDraft(Model):
    id: int = fields.BigIntField(pk=True)
    message: str = fields.TextField()
    date: datetime = fields.DatetimeField(default=datetime.now)
    dialog: models.Dialog = fields.ForeignKeyField("models.Dialog", on_delete=fields.CASCADE, unique=True)

    async def to_tl(self) -> DraftMessage:
        return DraftMessage(
            message=self.message,
            date=int(self.date.timestamp())
        )
