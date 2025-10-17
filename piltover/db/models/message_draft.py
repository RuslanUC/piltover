from __future__ import annotations

from datetime import datetime

from tortoise import fields, Model

from piltover.db import models
from piltover.tl import DraftMessage


class MessageDraft(Model):
    id: int = fields.BigIntField(pk=True)
    message: str = fields.TextField()
    date: datetime = fields.DatetimeField(default=datetime.now)
    dialog: models.Dialog = fields.OneToOneField("models.Dialog", on_delete=fields.CASCADE)

    def to_tl(self) -> DraftMessage:
        return DraftMessage(
            message=self.message,
            date=int(self.date.timestamp())
        )
