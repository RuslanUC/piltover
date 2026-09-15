from __future__ import annotations

from uuid import UUID, uuid4

from tortoise import fields, Model

from piltover.db import models


class UploadingFilePartBase(Model):
    id: int = fields.BigIntField(primary_key=True)
    part_id: int = fields.IntField()
    physical_id: UUID = fields.UUIDField(default=uuid4)
    size: int = fields.IntField()

    file: models.UploadingFileBase

    class Meta:
        abstract = True
