from __future__ import annotations

from tortoise import fields

from piltover.db import models
from piltover.db.models import UploadingFilePartBase


class UploadingFileSmallPart(UploadingFilePartBase):
    file: models.UploadingFileSmall = fields.ForeignKeyField("models.UploadingFileSmall", on_delete=fields.CASCADE)

    class Meta:
        unique_together = (
            ("file", "part_id"),
        )
