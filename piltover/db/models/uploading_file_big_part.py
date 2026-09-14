from __future__ import annotations

from tortoise import fields

from piltover.db import models
from piltover.db.models import UploadingFilePartBase


class UploadingFileBigPart(UploadingFilePartBase):
    file: models.UploadingFileBig = fields.ForeignKeyField("models.UploadingFileBig", on_delete=fields.CASCADE)

    class Meta:
        unique_together = (
            ("file", "part_id"),
        )
