from __future__ import annotations

from datetime import datetime
from time import mktime

from tortoise import fields

from piltover.db import models
from piltover.db.models._utils import Model
from piltover.tl_new import DraftMessage


class ReadState(Model):
    id: int = fields.BigIntField(pk=True)
    last_message_id: int = fields.BigIntField()
    dialog: models.Dialog = fields.ForeignKeyField("models.Dialog", on_delete=fields.CASCADE, unique=True)

