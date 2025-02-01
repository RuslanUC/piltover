from __future__ import annotations

from datetime import datetime, timedelta
from os import urandom

from tortoise import fields, Model

from piltover.db import models
from piltover.db.enums import MediaType
from piltover.tl import MessageMediaUnsupported, MessageMediaPhoto, MessageMediaDocument


def gen_access_hash() -> int:
    return int.from_bytes(urandom(8))


def gen_file_reference() -> bytes:
    return urandom(16)


def gen_expires() -> datetime:
    return datetime.now() + timedelta(days=7)


class MessageMedia(Model):
    id: int = fields.BigIntField(pk=True)
    spoiler: bool = fields.BooleanField(default=False)
    type: MediaType = fields.IntEnumField(MediaType, default=MediaType.DOCUMENT)
    file: models.File = fields.ForeignKeyField("models.File", on_delete=fields.CASCADE)

    async def to_tl(self, user: models.User) -> MessageMediaUnsupported | MessageMediaPhoto | MessageMediaDocument:
        self.file = await self.file

        if self.type == MediaType.DOCUMENT:
            return MessageMediaDocument(
                spoiler=self.spoiler,
                document=await self.file.to_tl_document(user),
            )
        elif self.type == MediaType.PHOTO:
            return MessageMediaPhoto(
                spoiler=self.spoiler,
                photo=await self.file.to_tl_photo(user),
            )

        return MessageMediaUnsupported()
