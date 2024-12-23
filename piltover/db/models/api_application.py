from __future__ import annotations

from os import urandom

from tortoise import fields

from piltover.db import models
from piltover.db.models._utils import Model


def gen_hash():
    return urandom(16).hex()


class ApiApplication(Model):
    id: int = fields.BigIntField(pk=True)
    hash: str = fields.CharField(max_length=32, default=gen_hash)
    name: str = fields.CharField(max_length=64)
    short_name: str = fields.CharField(max_length=32)
    owner: models.User = fields.ForeignKeyField("models.User", null=True, on_delete=fields.SET_NULL, unique=True)
