from __future__ import annotations

from piltover.db import models
from piltover.db.models import UploadingFileBase
from piltover.storage.base import StorageType, BaseStorage


class UploadingFileSmall(UploadingFileBase):
    PART_CLASS = models.UploadingFileSmallPart
    IS_SMALL = True

    class Meta:
        unique_together = (
            ("user", "file_id",),
        )

    async def _finalize(self, storage: BaseStorage, storage_type: StorageType, parts_num: int) -> None:
        # TODO: check md5
        await storage.finalize_small_upload_as(self.physical_id, storage_type, parts_num)
