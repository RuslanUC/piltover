from __future__ import annotations

from tortoise import fields

from piltover.db import models
from piltover.db.models import UploadingFileBase
from piltover.exceptions import ErrorRpc


class UploadingFileBig(UploadingFileBase):
    PART_CLASS = models.UploadingFileBigPart
    IS_SMALL = False

    total_parts: int = fields.IntField(default=0)
    part_size: int = fields.IntField(default=0)

    class Meta:
        unique_together = (
            ("user", "file_id",),
        )

    def check_parts_count(self, parts: list[models.UploadingFilePartBase]) -> None:
        if (self.total_parts > 0 and self.total_parts != len(parts)) or not parts:
            reason = ""
            if self.total_parts != len(parts):
                reason = f"{self.total_parts} != len({parts})"
            elif not parts:
                reason = f"not {parts}"
            raise ErrorRpc(error_code=400, error_message="FILE_PARTS_INVALID", reason=reason)
