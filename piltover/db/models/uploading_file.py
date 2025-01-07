from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from tortoise import fields, Model

from piltover.db import models


class UploadingFile(Model):
    id: int = fields.BigIntField(pk=True)
    file_id: str = fields.CharField(index=True, max_length=64)
    total_parts: int = fields.IntField(default=0)
    created_at: datetime = fields.DatetimeField(default=datetime.now)
    user: models.User = fields.ForeignKeyField("models.User", on_delete=fields.CASCADE)


class UploadingFilePart(Model):
    id: int = fields.BigIntField(pk=True)
    part_id: int = fields.IntField()
    physical_id: UUID = fields.UUIDField(default=uuid4)
    size: int = fields.IntField()
    file: UploadingFile = fields.ForeignKeyField("models.UploadingFile", on_delete=fields.CASCADE)
