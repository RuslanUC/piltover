from __future__ import annotations

from datetime import datetime
from io import BytesIO
from uuid import UUID, uuid4

from tortoise import fields, Model

from piltover.db import models
from piltover.db.enums import FileType
from piltover.exceptions import ErrorRpc
from piltover.storage.base import BaseStorage, StorageType


class UploadingFile(Model):
    id: int = fields.BigIntField(pk=True)
    file_id: str = fields.CharField(index=True, max_length=64)
    physical_id: UUID = fields.UUIDField(default=uuid4)
    total_parts: int = fields.IntField(default=0)
    created_at: datetime = fields.DatetimeField(default=datetime.now)
    mime: str | None = fields.CharField(max_length=64, null=True, default=None)
    user: models.User = fields.ForeignKeyField("models.User", on_delete=fields.CASCADE)

    class Meta:
        unique_together = (
            ("user", "file_id",),
        )

    async def finalize_upload(
            self, storage: BaseStorage, fallback_mime: str, attributes: list | None = None,
            file_type: FileType = FileType.DOCUMENT, parts_num: int | None = None, force_fallback_mime: bool = False,
            thumb_bytes: bytes | None = None,
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

        if parts[0].part_id != 0:
            raise ErrorRpc(error_code=400, error_message=f"FILE_PART_0_MISSING")

        size = parts[0].size
        for idx in range(1, len(parts)):
            part = parts[idx]
            if part.part_id - 1 != parts[idx - 1].part_id:
                raise ErrorRpc(error_code=400, error_message=f"FILE_PART_{part.part_id - 1}_MISSING")
            size += part.size

        file = models.File(
            physical_id=self.physical_id,
            mime_type=fallback_mime if self.mime is None or force_fallback_mime else self.mime,
            size=size,
            type=file_type,
        )
        if attributes:
            await file.parse_attributes_from_tl(attributes)

        if file_type is FileType.PHOTO:
            finalize_as = StorageType.PHOTO
            component = storage.photos
        else:
            finalize_as = StorageType.DOCUMENT
            component = storage.documents

        await storage.finalize_upload_as(self.physical_id, finalize_as, len(parts))

        if not force_fallback_mime and self.mime is not None and self.mime.startswith("video/"):
            from piltover.app.utils.utils import extract_video_metadata

            location = await component.get_location(self.physical_id)
            duration, has_video, has_audio, thumb = await extract_video_metadata(location)
            if duration > 0:
                file.duration = duration
            if thumb is not None and thumb_bytes is None:
                thumb_file = BytesIO()
                thumb.save(thumb_file, format="JPEG")
                thumb_bytes = thumb_file.getbuffer()

        await file.make_thumbs(storage, thumb_bytes)
        await file.save()

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
