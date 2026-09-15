from __future__ import annotations

from piltover.db import models
from piltover.db.models import UploadingFileBase


class UploadingFileSmall(UploadingFileBase):
    PART_CLASS = models.UploadingFileSmallPart
    IS_SMALL = True

    class Meta:
        unique_together = (
            ("user", "file_id",),
        )
