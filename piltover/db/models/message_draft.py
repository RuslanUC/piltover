from __future__ import annotations

from datetime import datetime

from tortoise import fields

from piltover.db import models
from piltover.db.models._utils import Model


class MessageDraft(Model):
    id: int = fields.BigIntField(pk=True)
    message: str = fields.TextField()
    date: datetime = fields.DatetimeField(default=datetime.now)
    dialog: models.Dialog = fields.ForeignKeyField("models.Dialog", on_delete=fields.CASCADE)

    #reply_to: models.Message = fields.ForeignKeyField("models.Message", null=True, default=None, on_delete=fields.SET_NULL)  # ??
