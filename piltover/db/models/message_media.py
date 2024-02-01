from __future__ import annotations

from datetime import datetime, timedelta
from os import urandom

from tortoise import fields

from piltover.db import models
from piltover.db.enums import MediaType
from piltover.db.models._utils import Model


def gen_access_hash() -> int:
    return int.from_bytes(urandom(8))


def gen_file_reference() -> bytes:
    return urandom(16)


def gen_expires() -> datetime:
    return datetime.now() + timedelta(days=7)


class MessageMedia(Model):
    id: int = fields.BigIntField(pk=True)
    spoiler: bool = fields.BooleanField(default=False)
    type: MediaType = fields.IntEnumField(MediaType, default=MediaType.DOCUMENT)
    file: models.File = fields.ForeignKeyField("models.File", on_delete=fields.CASCADE)
    message: models.Message = fields.ForeignKeyField("models.Message", on_delete=fields.CASCADE, unique=True)
