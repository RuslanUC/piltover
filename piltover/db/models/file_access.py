from __future__ import annotations

from datetime import datetime, timedelta
from os import urandom

from tortoise import fields

from piltover.db import models
from piltover.db.models._utils import Model


def gen_access_hash() -> int:
    return int.from_bytes(urandom(7))


def gen_file_reference() -> bytes:
    return urandom(16)


def gen_expires() -> datetime:
    return datetime.now() + timedelta(days=7)


class FileAccess(Model):
    id: int = fields.BigIntField(pk=True)
    access_hash: int = fields.BigIntField(default=gen_access_hash)
    file_reference: bytes = fields.BinaryField(default=gen_file_reference)
    expires: datetime = fields.DatetimeField(default=gen_expires)
    file: models.File = fields.ForeignKeyField("models.File", on_delete=fields.CASCADE)
    user: models.User = fields.ForeignKeyField("models.User", on_delete=fields.CASCADE)
