from __future__ import annotations

from time import time

from tortoise import fields

from piltover.db import models
from piltover.db.models._utils import Model


def gen_date() -> int:
    return int(time())


class Update(Model):
    id: int = fields.BigIntField(pk=True)
    pts: int = fields.BigIntField()
    date: int = fields.BigIntField(default=gen_date)
    update_type: int = fields.BigIntField()
    update_data: bytes = fields.BinaryField()
    user_ids_to_fetch: list[int] = fields.JSONField(null=True, default=None)
    user: models.User = fields.ForeignKeyField("models.User", on_delete=fields.CASCADE)
