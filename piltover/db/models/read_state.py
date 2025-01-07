from __future__ import annotations

from tortoise import fields, Model

from piltover.db import models


class ReadState(Model):
    id: int = fields.BigIntField(pk=True)
    last_message_id: int = fields.BigIntField()
    dialog: models.Dialog = fields.ForeignKeyField("models.Dialog", on_delete=fields.CASCADE, unique=True)

