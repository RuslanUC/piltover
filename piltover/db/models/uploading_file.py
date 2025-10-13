from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

import aiofiles
from tortoise import fields, Model

from piltover.db import models
from piltover.db.enums import FileType
from piltover.exceptions import ErrorRpc


class UploadingFile(Model):
    id: int = fields.BigIntField(pk=True)
    file_id: str = fields.CharField(index=True, max_length=64)
    total_parts: int = fields.IntField(default=0)
    created_at: datetime = fields.DatetimeField(default=datetime.now)
    mime: str | None = fields.CharField(max_length=64, null=True, default=None)
    user: models.User = fields.ForeignKeyField("models.User", on_delete=fields.CASCADE)

    class Meta:
        unique_together = (
            ("user", "file_id",),
        )

    async def finalize_upload(
            self, files_dir: Path, fallback_mime: str, attributes: list | None = None,
            file_type: FileType = FileType.DOCUMENT, parts_num: int | None = None, force_fallback_mime: bool = False,
    ) -> models.File:
        parts = await UploadingFilePart.filter(file=self).order_by("part_id")
        if (self.total_parts > 0 and self.total_parts != len(parts)) or not parts:
            reason = ""
            if self.total_parts != len(parts):
                reason = f"{self.total_parts} != len({parts})"
            elif not parts:
                reason = f"not {parts}"
            raise ErrorRpc(error_code=400, error_message="FILE_PARTS_INVALID", reason=reason)

        if parts_num is not None and parts_num != len(parts):
            raise ErrorRpc(error_code=400, error_message="FILE_PARTS_INVALID", reason=f"{parts_num} != len({parts})")

        size = parts[0].size
        for idx, part in enumerate(parts):
            if idx == 0:
                continue
            if part.part_id - 1 != parts[idx - 1].part_id:
                raise ErrorRpc(error_code=400, error_message=f"FILE_PART_{part.part_id - 1}_MISSING")
            size += part.size

        file = models.File(
            mime_type=fallback_mime if self.mime is None or force_fallback_mime else self.mime,
            size=size,
            type=file_type,
        )
        if attributes:
            await file.parse_attributes_from_tl(attributes)
        await file.save()

        async with aiofiles.open(files_dir / f"{file.physical_id}", "wb") as f_out:
            for part in parts:
                async with aiofiles.open(files_dir / "parts" / f"{part.physical_id}_{part.part_id}", "rb") as f_part:
                    await f_out.write(await f_part.read())

        return file


class UploadingFilePart(Model):
    id: int = fields.BigIntField(pk=True)
    part_id: int = fields.IntField()
    physical_id: UUID = fields.UUIDField(default=uuid4)
    size: int = fields.IntField()
    file: UploadingFile = fields.ForeignKeyField("models.UploadingFile", on_delete=fields.CASCADE)

    class Meta:
        unique_together = (
            ("file", "part_id"),
        )
