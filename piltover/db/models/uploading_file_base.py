from __future__ import annotations

from datetime import datetime
from io import BytesIO
from uuid import UUID, uuid4

from tortoise import Model, fields

from piltover.db import models
from piltover.db.enums import FileType
from piltover.exceptions import ErrorRpc
from piltover.storage import BaseStorage
from piltover.storage.base import StorageType
from piltover.tl import InputFile, InputFileBig
from piltover.utils.debug import measure_time


class UploadingFileBase(Model):
    id: int = fields.BigIntField(primary_key=True)
    file_id: int = fields.BigIntField()
    physical_id: UUID = fields.UUIDField(default=uuid4)
    created_at: datetime = fields.DatetimeField(auto_now_add=True)
    mime: str | None = fields.CharField(max_length=64, null=True, default=None)
    user: models.User = fields.ForeignKeyField("models.User", on_delete=fields.CASCADE)

    PART_CLASS: models.UploadingFilePartBase
    IS_SMALL: bool

    class Meta:
        abstract = True

    @staticmethod
    async def get_from_input(user_id: int, input_file: InputFile | InputFileBig) -> UploadingFileBase | None:
        if isinstance(input_file, InputFile):
            return await models.UploadingFileSmall.get_or_none(user_id=user_id, file_id=input_file.id)
        elif isinstance(input_file, InputFileBig):
            return await models.UploadingFileBig.get_or_none(user_id=user_id, file_id=input_file.id)
        else:
            raise TypeError("Expected either InputFile or InputFileBig")

    async def finalize_upload(
            self, storage: BaseStorage, fallback_mime: str, attributes: list | None = None,
            file_type: FileType = FileType.DOCUMENT, parts_num: int | None = None, force_fallback_mime: bool = False,
            thumb_bytes: bytes | None = None, profile_photo: bool = False,
    ) -> models.File:
        parts = await self.PART_CLASS.filter(file=self).order_by("part_id")
        if isinstance(self, models.UploadingFileBig):
            self.check_parts_count(parts)

        if parts_num is not None and parts_num != len(parts):
            raise ErrorRpc(error_code=400, error_message="FILE_PARTS_INVALID", reason=f"{parts_num} != len({parts})")

        if parts[0].part_id != 0:
            raise ErrorRpc(error_code=400, error_message="FILE_PART_0_MISSING")

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
            file.parse_attributes_from_tl(attributes)

        if file_type is FileType.PHOTO:
            finalize_as = StorageType.PHOTO
            component = storage.photos
        else:
            finalize_as = StorageType.DOCUMENT
            component = storage.documents

        with measure_time("storage.finalize_*_upload_as"):
            if self.IS_SMALL:
                await storage.finalize_small_upload_as(self.physical_id, finalize_as, len(parts))
            else:
                await storage.finalize_big_upload_as(self.physical_id, finalize_as, len(parts))

        if not force_fallback_mime and self.mime is not None and self.mime.startswith("video/"):
            from piltover.app.utils.utils import extract_video_metadata

            location = await component.get_location(self.physical_id)
            duration, _, _, thumb = await extract_video_metadata(location)
            if duration > 0:
                file.duration = duration
            if thumb is not None and thumb_bytes is None:
                thumb_file = BytesIO()
                thumb.save(thumb_file, format="JPEG")
                thumb_bytes = thumb_file.getbuffer()

        await file.make_thumbs(storage, thumb_bytes, profile_photo)
        await file.save()

        return file
