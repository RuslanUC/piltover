from __future__ import annotations

from base64 import b85encode, b85decode
from datetime import datetime
from io import BytesIO
from uuid import UUID, uuid4

from tortoise import fields, Model

from piltover.db import models
from piltover.db.enums import FileType
from piltover.tl import DocumentAttributeImageSize, DocumentAttributeAnimated, DocumentAttributeVideo, TLObject, \
    DocumentAttributeAudio, DocumentAttributeFilename, Document as TLDocument, Photo as TLPhoto, PhotoStrippedSize, \
    PhotoSize, DocumentAttributeSticker, InputStickerSetEmpty, PhotoPathSize, Long, InputStickerSetID, MaskCoords


class File(Model):
    id: int = fields.BigIntField(pk=True)
    physical_id: UUID = fields.UUIDField(default=uuid4)
    created_at: datetime = fields.DatetimeField(default=datetime.now)
    mime_type: str = fields.CharField(max_length=200)
    size: int = fields.BigIntField()
    type: FileType = fields.IntEnumField(FileType)

    constant_access_hash: int | None = fields.BigIntField(null=True, default=None)
    constant_file_ref: UUID | None = fields.UUIDField(null=True, default=None)

    # DocumentAttributeFilename
    filename: str | None = fields.TextField(null=True, default=None)
    # DocumentAttributeImageSize, DocumentAttributeVideo
    width: int | None = fields.IntField(null=True, default=None)
    height: int | None = fields.IntField(null=True, default=None)
    # DocumentAttributeVideo, DocumentAttributeAudio
    duration: float | None = fields.FloatField(null=True, default=None)
    # DocumentAttributeVideo
    supports_streaming: bool = fields.BooleanField(default=False)
    nosound: bool = fields.BooleanField(default=False)
    preload_prefix_size: int | None = fields.IntField(null=True, default=None)
    # DocumentAttributeAudio
    title: str | None = fields.TextField(null=True, default=None)
    performer: str | None = fields.TextField(null=True, default=None)

    # Photo
    photo_sizes: list[dict[str, str | int]] | None = fields.JSONField(null=True, default=None)
    photo_stripped: bytes | None = fields.BinaryField(null=True, default=None)
    photo_path: bytes | None = fields.BinaryField(null=True, default=None)

    # DocumentAttributeSticker
    stickerset: models.Stickerset | None = fields.ForeignKeyField("models.Stickerset", null=True, default=None, on_delete=fields.SET_NULL)
    sticker_pos: int | None = fields.IntField(null=True, default=None)
    sticker_alt: str | None = fields.CharField(max_length=32, null=True, default=None)
    sticker_is_mask: bool = fields.BooleanField(default=False)
    sticker_mask_coords: str | None = fields.CharField(max_length=36, null=True, default=None)

    stickerset_id: int | None

    @property
    def sticker_mask_coords_tl(self) -> MaskCoords | None:
        if not self.sticker_is_mask or self.sticker_mask_coords is None:
            return None
        return MaskCoords.deserialize(BytesIO(b85decode(self.sticker_mask_coords)))

    async def parse_attributes_from_tl(self, attributes: list[TLObject]) -> None:
        for attribute in attributes:
            if isinstance(attribute, DocumentAttributeImageSize):
                self.width = attribute.w
                self.height = attribute.h
            elif isinstance(attribute, DocumentAttributeAnimated):
                self.type = FileType.DOCUMENT_GIF
            elif isinstance(attribute, DocumentAttributeVideo):
                self.type = FileType.DOCUMENT_VIDEO_NOTE if attribute.round_message else FileType.DOCUMENT_VIDEO
                self.width = attribute.w
                self.height = attribute.h
                self.duration = attribute.duration
                self.supports_streaming = attribute.supports_streaming
                self.nosound = attribute.nosound
                self.preload_prefix_size = attribute.preload_prefix_size
            elif isinstance(attribute, DocumentAttributeAudio):
                self.type = FileType.DOCUMENT_VOICE if attribute.voice else FileType.DOCUMENT_AUDIO
                self.duration = attribute.duration
                self.title = attribute.title
                self.performer = attribute.performer
            elif isinstance(attribute, DocumentAttributeSticker):
                self.type = FileType.DOCUMENT_STICKER
                self.stickerset = await models.Stickerset.from_input(attribute.stickerset)
                self.sticker_alt = attribute.alt
                self.sticker_is_mask = attribute.mask
                if attribute.mask and attribute.mask_coords is not None:
                    self.sticker_mask_coords = b85encode(attribute.mask_coords.serialize()).decode("utf8")
            elif isinstance(attribute, DocumentAttributeFilename):
                self.filename = attribute.file_name

    def attributes_to_tl(self) -> list:
        result = []

        if self.filename:
            result.append(DocumentAttributeFilename(file_name=self.filename))
        if self.type not in (FileType.DOCUMENT_VIDEO_NOTE, FileType.DOCUMENT_VIDEO) and self.width and self.height:
            result.append(DocumentAttributeImageSize(w=self.width, h=self.height))
        elif self.type in (FileType.DOCUMENT_VIDEO_NOTE, FileType.DOCUMENT_VIDEO):
            result.append(DocumentAttributeVideo(
                duration=self.duration,
                w=self.width,
                h=self.height,
                round_message=self.type is FileType.DOCUMENT_VIDEO,
                supports_streaming=self.supports_streaming,
                nosound=self.nosound,
                preload_prefix_size=self.preload_prefix_size,
            ))
        elif self.type is FileType.DOCUMENT_STICKER:
            stickerset = InputStickerSetEmpty()
            if self.stickerset is not None:
                stickerset = InputStickerSetID(id=self.stickerset.id, access_hash=self.stickerset.access_hash)
            result.append(DocumentAttributeSticker(
                alt=self.sticker_alt or "",
                stickerset=stickerset,
                mask=self.sticker_is_mask,
                mask_coords=self.sticker_mask_coords_tl,
            ))
        if self.type is FileType.DOCUMENT_GIF:
            result.append(DocumentAttributeAnimated())
        if self.type in (FileType.DOCUMENT_AUDIO, FileType.DOCUMENT_VOICE):
            result.append(DocumentAttributeAudio(
                duration=int(self.duration),
                voice=self.type is FileType.DOCUMENT_VOICE,
                title=self.title,
                performer=self.performer,
            ))

        return result

    async def to_tl_document(self, user: models.User) -> TLDocument:
        if self.constant_access_hash is None or self.constant_file_ref is None:
            await user.load_if_lazy()
            access, _ = await models.FileAccess.get_or_create(user=user, file=self)
            access_hash = access.access_hash
            file_ref = access.create_file_ref()
        else:
            access_hash = self.constant_access_hash
            file_ref = models.FileAccess.CONST_FILE_REF_ID_BYTES + Long.write(self.id) + self.constant_file_ref.bytes

        # TODO: fetch when fetching file
        if self.stickerset is not None:
            self.stickerset = await self.stickerset

        return TLDocument(
            id=self.id,
            access_hash=access_hash,
            file_reference=file_ref,
            date=int(self.created_at.timestamp()),
            mime_type=self.mime_type,
            size=self.size,
            dc_id=2,
            attributes=self.attributes_to_tl(),
        )

    async def to_tl_photo(self, user: models.User) -> TLPhoto:
        if self.constant_access_hash is None or self.constant_file_ref is None:
            await user.load_if_lazy()
            access, _ = await models.FileAccess.get_or_create(user=user, file=self)
            access_hash = access.access_hash
            file_ref = access.create_file_ref()
        else:
            access_hash = self.constant_access_hash
            file_ref = models.FileAccess.CONST_FILE_REF_ID_BYTES + Long.write(self.id) + self.constant_file_ref.bytes

        sizes: list[PhotoStrippedSize | PhotoSize | PhotoPathSize]
        sizes = [PhotoSize(**size) for size in self.photo_sizes]
        if self.photo_stripped:
            sizes.insert(0, PhotoStrippedSize(type_="i", bytes_=self.photo_stripped))
        if self.photo_path:
            sizes.insert(0, PhotoPathSize(type_="j", bytes_=self.photo_path))

        return TLPhoto(
            id=self.id,
            access_hash=access_hash,
            file_reference=file_ref,
            date=int(self.created_at.timestamp()),
            sizes=sizes,
            dc_id=2,
            video_sizes=[],
        )
