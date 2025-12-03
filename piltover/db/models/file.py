from __future__ import annotations

import hashlib
import hmac
from base64 import b85encode, b85decode
from datetime import datetime
from io import BytesIO
from time import time
from typing import Self
from uuid import UUID, uuid4

from PIL import UnidentifiedImageError
from tortoise import fields, Model
from tortoise.expressions import Q

from piltover.app_config import AppConfig
from piltover.context import request_ctx
from piltover.db import models
from piltover.db.enums import FileType
from piltover.exceptions import Unreachable
from piltover.storage import BaseStorage
from piltover.storage.base import StorageBuffer, StorageType
from piltover.tl import DocumentAttributeImageSize, DocumentAttributeAnimated, DocumentAttributeVideo, TLObject, \
    DocumentAttributeAudio, DocumentAttributeFilename, Document as TLDocument, Photo as TLPhoto, PhotoStrippedSize, \
    PhotoSize, DocumentAttributeSticker, InputStickerSetEmpty, PhotoPathSize, Long, InputStickerSetID, MaskCoords, \
    DocumentAttributeVideo_133, DocumentAttributeVideo_160, DocumentAttributeVideo_185, Int, \
    DocumentAttributeCustomEmoji
from piltover.tl.base import PhotoSizeInst
from piltover.tl.types.internal_access import AccessHashPayloadFile, FileReferencePayload

VIDEO_ATTRIBUTES = (
    DocumentAttributeVideo, DocumentAttributeVideo_133, DocumentAttributeVideo_160, DocumentAttributeVideo_185,
)


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
    waveform: bytes | None = fields.BinaryField(null=True, default=None)

    # Photo or thumbs
    photo_sizes: list[dict[str, str | int]] | None = fields.JSONField(null=True, default=None)
    photo_stripped: bytes | None = fields.BinaryField(null=True, default=None)
    photo_path: bytes | None = fields.BinaryField(null=True, default=None)

    # DocumentAttributeSticker, DocumentAttributeCustomEmoji
    stickerset: models.Stickerset | None = fields.ForeignKeyField("models.Stickerset", null=True, default=None, on_delete=fields.SET_NULL)
    sticker_pos: int | None = fields.IntField(null=True, default=None)
    sticker_alt: str | None = fields.CharField(max_length=32, null=True, default=None)
    sticker_is_mask: bool = fields.BooleanField(default=False)
    sticker_mask_coords: str | None = fields.CharField(max_length=36, null=True, default=None)

    stickerset_id: int | None

    needs_save: bool = False

    def __repr__(self) -> str:
        self_fields = ", ".join(f"{field}={getattr(self, field)!r}" for field in self._meta.db_fields)
        return f"{self.__class__.__name__}({self_fields})"

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
                if self.type is FileType.DOCUMENT:
                    self.type = FileType.DOCUMENT_GIF
            elif isinstance(attribute, VIDEO_ATTRIBUTES):
                self.type = FileType.DOCUMENT_VIDEO_NOTE if attribute.round_message else FileType.DOCUMENT_VIDEO
                self.width = attribute.w
                self.height = attribute.h
                self.duration = attribute.duration
                self.supports_streaming = attribute.supports_streaming
                if not isinstance(attribute, DocumentAttributeVideo_133):
                    self.nosound = attribute.nosound
                    self.preload_prefix_size = attribute.preload_prefix_size
            elif isinstance(attribute, DocumentAttributeAudio):
                self.type = FileType.DOCUMENT_VOICE if attribute.voice else FileType.DOCUMENT_AUDIO
                self.duration = attribute.duration
                if attribute.voice:
                    self.waveform = attribute.waveform[:64]
                else:
                    self.title = attribute.title
                    self.performer = attribute.performer
            # TODO: remove this since sticker attributes are set when sticker is created?
            #  Or just dont set `stickerset`?
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

        if self.type not in (FileType.DOCUMENT_VIDEO_NOTE, FileType.DOCUMENT_VIDEO) and self.width and self.height:
            result.append(DocumentAttributeImageSize(w=self.width, h=self.height))
        elif self.type in (FileType.DOCUMENT_VIDEO_NOTE, FileType.DOCUMENT_VIDEO):
            result.append(DocumentAttributeVideo(
                duration=self.duration,
                w=self.width,
                h=self.height,
                round_message=self.type is FileType.DOCUMENT_VIDEO_NOTE,
                supports_streaming=self.supports_streaming,
                nosound=self.nosound,
                preload_prefix_size=self.preload_prefix_size,
            ))
        if self.type is FileType.DOCUMENT_STICKER:
            stickerset_ = InputStickerSetEmpty()
            if self.stickerset_id is not None and not self.stickerset.deleted:
                stickerset_ = InputStickerSetID(id=self.stickerset.id, access_hash=self.stickerset.access_hash)
            result.append(DocumentAttributeSticker(
                alt=self.sticker_alt or "",
                stickerset=stickerset_,
                mask=self.sticker_is_mask,
                mask_coords=self.sticker_mask_coords_tl,
            ))
        if self.type is FileType.DOCUMENT_EMOJI:
            stickerset_ = InputStickerSetEmpty()
            if self.stickerset_id is not None and not self.stickerset.deleted:
                stickerset_ = InputStickerSetID(id=self.stickerset.id, access_hash=self.stickerset.access_hash)
            result.append(DocumentAttributeCustomEmoji(
                alt=self.sticker_alt or "",
                stickerset=stickerset_,
                free=True,
            ))
        if self.type is FileType.DOCUMENT_GIF:
            result.append(DocumentAttributeAnimated())
        if self.type in (FileType.DOCUMENT_AUDIO, FileType.DOCUMENT_VOICE):
            result.append(DocumentAttributeAudio(
                duration=int(self.duration),
                voice=self.type is FileType.DOCUMENT_VOICE,
                title=self.title,
                performer=self.performer,
                waveform=self.waveform,
            ))
        if self.filename:
            result.append(DocumentAttributeFilename(file_name=self.filename))

        return result

    async def make_thumbs(
            self, storage: BaseStorage, thumb_bytes: StorageBuffer | None = None, profile_photo: bool = False,
    ) -> None:
        from piltover.app.utils.utils import resize_photo, generate_stripped

        thumb_suffix = None
        has_thumbnail = False
        is_document = True

        if self.type is not FileType.PHOTO and thumb_bytes is not None:
            await storage.save_part(self.physical_id, 0, thumb_bytes, True, "thumb")
            await storage.finalize_upload_as(self.physical_id, StorageType.PHOTO, 0, "thumb")
            thumb_suffix = "thumb"
            has_thumbnail = True
            is_document = False
        elif self.type is FileType.PHOTO or self.mime_type.startswith("image/"):
            has_thumbnail = True
            is_document = self.type is not FileType.PHOTO

        if not has_thumbnail:
            return

        try:
            self.photo_sizes = await resize_photo(
                storage, self.physical_id, suffix=thumb_suffix, is_document=is_document,
                sizes="abc" if profile_photo else "m",
            )
            self.photo_stripped = await generate_stripped(
                storage, self.physical_id, suffix=thumb_suffix, is_document=is_document,
            )
        except UnidentifiedImageError:
            self.mime_type = "application/octet-stream"

    def _to_tl_thumbs(self) -> list[PhotoSizeInst]:
        sizes: list[PhotoStrippedSize | PhotoSize | PhotoPathSize]
        sizes = [PhotoSize(**size) for size in self.photo_sizes] if self.photo_sizes else []
        if self.photo_stripped:
            sizes.insert(0, PhotoStrippedSize(type_="i", bytes_=self.photo_stripped))
        if self.photo_path:
            sizes.insert(0, PhotoPathSize(type_="j", bytes_=self.photo_path))

        return sizes

    def _make_hash_and_ref(self) -> tuple[int, bytes]:
        if self.constant_access_hash is None or self.constant_file_ref is None:
            return -1, FileReferencePayload(file_id=self.id, created_at=0).write()
        else:
            return (
                self.constant_access_hash,
                self.CONST_FILE_REF_ID_BYTES + Long.write(self.id) + self.constant_file_ref.bytes
            )

    def to_tl_document(self) -> TLDocument:
        access_hash, file_ref = self._make_hash_and_ref()

        return TLDocument(
            id=self.id,
            access_hash=access_hash,
            file_reference=file_ref,
            date=int(self.created_at.timestamp()),
            mime_type=self.mime_type,
            size=self.size,
            dc_id=2,
            attributes=self.attributes_to_tl(),
            thumbs=self._to_tl_thumbs(),
        )

    def to_tl_photo(self) -> TLPhoto:
        access_hash, file_ref = self._make_hash_and_ref()

        return TLPhoto(
            id=self.id,
            access_hash=access_hash,
            file_reference=file_ref,
            date=int(self.created_at.timestamp()),
            sizes=self._to_tl_thumbs(),
            dc_id=2,
            video_sizes=[],
        )

    # constantFileReference file_id:long file_ref:bytes = ConstantFileReference
    CONST_FILE_REF_ID = 0x51a32644
    CONST_FILE_REF_ID_BYTES = Int.write(CONST_FILE_REF_ID, signed=False)
    PLACEHOLDER_FILE_REF_ID_BYTES = Int.write(FileReferencePayload.tlid(), signed=False)

    @staticmethod
    def is_file_ref_valid(file_ref: bytes, user_id: int | None = None, file_id: int | None = None) -> tuple[bool, bool]:
        if file_ref.startswith(File.PLACEHOLDER_FILE_REF_ID_BYTES):
            raise Unreachable("Placeholder file_reference was not replaced and client got it")

        if len(file_ref) == (4 + 8 + 16) and file_ref.startswith(File.CONST_FILE_REF_ID_BYTES):
            valid = file_ref[4:12] == Long.write(file_id)
            return valid, valid

        if len(file_ref) != (4 + 256 // 8):
            return False, False

        now_minutes = time() // 60
        created_at = Int.read_bytes(file_ref[:4])
        if (created_at + AppConfig.FILE_REF_EXPIRE_MINUTES) < now_minutes:
            return False, False

        if user_id is not None and file_id is not None:
            payload = Long.write(user_id) + Long.write(file_id) + file_ref[:4]

            if hmac.new(AppConfig.HMAC_KEY, payload, hashlib.sha256).digest() != file_ref[4:]:
                return False, False

        return True, False

    @staticmethod
    def make_access_hash(user: int, auth: int, file: int) -> int:
        to_sign = AccessHashPayloadFile(this_user_id=user, file_id=file, auth_id=auth).write()
        digest = hmac.new(AppConfig.HMAC_KEY, to_sign, hashlib.sha256).digest()
        return Long.read_bytes(digest[-8:])

    @staticmethod
    def check_access_hash(user: int, auth: int, file: int, access_hash: int) -> bool:
        return File.make_access_hash(user, auth, file) == access_hash

    @staticmethod
    def make_file_reference(user: int, file: int, created_at: int) -> bytes:
        created_at = Int.write(created_at)
        payload = Long.write(user) + Long.write(file) + created_at
        return created_at + hmac.new(AppConfig.HMAC_KEY, payload, hashlib.sha256).digest()

    @classmethod
    async def from_input(
            cls, user_id: int, file_id: int, access_hash: int, file_reference: bytes,
            type_: FileType | None = None, mimes: list[str] | None = None, add_query: Q | None = None,
    ) -> Self | None:
        valid, const = File.is_file_ref_valid(file_reference, user_id, file_id)
        if not valid:
            return None

        file_q = Q(id=file_id)
        if type_ is not None:
            file_q &= Q(type=type_)
        if mimes is not None:
            file_q &= Q(mime_type__in=mimes)
        if add_query is not None:
            file_q &= add_query

        if const:
            file_q &= Q(
                constant_access_hash=access_hash,
                constant_file_ref=UUID(bytes=file_reference[12:]),
            )
        else:
            ctx = request_ctx.get()
            if not File.check_access_hash(user_id, ctx.auth_id, file_id, access_hash):
                return None

        return await File.get_or_none(file_q)
