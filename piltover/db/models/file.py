from __future__ import annotations

from datetime import datetime
from time import mktime
from uuid import UUID, uuid4

from tortoise import fields

from piltover.db import models
from piltover.db.enums import FileType
from piltover.db.models._utils import Model
from piltover.tl import DocumentAttributeImageSize, DocumentAttributeAnimated, \
    DocumentAttributeVideo, DocumentAttributeAudio, DocumentAttributeFilename, Document as TLDocument, Photo as TLPhoto, \
    PhotoStrippedSize, PhotoSize

attribute_name_to_cls = {
    "image_size": DocumentAttributeImageSize,
    "animated": DocumentAttributeAnimated,
    "video": DocumentAttributeVideo,
    "audio": DocumentAttributeAudio,
    "filename": DocumentAttributeFilename,
}


class File(Model):
    id: int = fields.BigIntField(pk=True)
    physical_id: UUID = fields.UUIDField(default=uuid4)
    created_at: datetime = fields.DatetimeField(default=datetime.now)
    mime_type: str = fields.CharField(max_length=200)
    size: int = fields.BigIntField()
    type: FileType = fields.IntEnumField(FileType)
    attributes: dict = fields.JSONField(default={})

    @staticmethod
    def attributes_from_tl(attributes: list) -> dict:
        result = {}
        for attribute in attributes:
            if isinstance(attribute, DocumentAttributeImageSize) and "image_size" not in result:
                result["image_size"] = {"w": attribute.w, "h": attribute.h}
            elif isinstance(attribute, DocumentAttributeAnimated) and "animated" not in result:
                result["animated"] = {}
            elif isinstance(attribute, DocumentAttributeVideo) and "video" not in result:
                result["video"] = {"round_message": attribute.round_message,
                                   "supports_streaming": attribute.supports_streaming, "nosound": attribute.nosound,
                                   "duration": attribute.duration, "w": attribute.w, "h": attribute.h}
            elif isinstance(attribute, DocumentAttributeAudio) and "audio" not in result:
                result["audio"] = {"voice": attribute.voice, "duration": attribute.duration,
                                   "title": attribute.title, "performer": attribute.performer}
            if isinstance(attribute, DocumentAttributeFilename) and "filename" not in result:
                result["filename"] = {"file_name": attribute.file_name}

        return result

    def attributes_to_tl(self) -> list:
        result = []
        for attribute, value in self.attributes.items():
            if attribute not in attribute_name_to_cls:
                continue
            result.append(attribute_name_to_cls[attribute](**value))

        return result

    async def to_tl_document(self, user: models.User) -> TLDocument:
        access = await models.FileAccess.get_or_renew(user, self)

        return TLDocument(
            id=self.id,
            access_hash=access.access_hash,
            file_reference=access.file_reference,
            date=int(mktime(self.created_at.timetuple())),
            mime_type=self.mime_type,
            size=self.size,
            dc_id=2,
            attributes=self.attributes_to_tl(),
        )

    async def to_tl_photo(self, user: models.User) -> TLPhoto:
        access = await models.FileAccess.get_or_renew(user, self)

        sizes: list[PhotoStrippedSize | PhotoSize]
        sizes = [PhotoSize(**size) for size in self.attributes.get("_sizes", [])]
        if "_size_stripped" in self.attributes:
            sizes.insert(0, PhotoStrippedSize(
                type_="i",
                bytes_=bytes.fromhex(self.attributes["_size_stripped"])
            ))

        return TLPhoto(
            id=self.id,
            access_hash=access.access_hash,
            file_reference=access.file_reference,
            date=int(mktime(self.created_at.timetuple())),
            sizes=sizes,
            dc_id=2,
            video_sizes=[],
        )
