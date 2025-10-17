from __future__ import annotations

from datetime import datetime, timedelta
from os import urandom

from tortoise import fields, Model

from piltover.db import models
from piltover.db.enums import MediaType
from piltover.tl import MessageMediaUnsupported, MessageMediaPhoto, MessageMediaDocument, MessageMediaPoll

MessageMediaTypes = MessageMediaUnsupported | MessageMediaPhoto | MessageMediaDocument | MessageMediaPoll


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
    file: models.File | None = fields.ForeignKeyField("models.File", null=True, default=None)
    poll: models.Poll | None = fields.ForeignKeyField("models.Poll", null=True, default=None)

    file_id: int | None
    poll_id: int | None

    async def to_tl(self, user: models.User) -> MessageMediaTypes:
        if self.type in (MediaType.DOCUMENT, MediaType.PHOTO):
            self.file = await self.file
        elif self.type is MediaType.POLL:
            self.poll = await self.poll

        if self.type is MediaType.DOCUMENT:
            return MessageMediaDocument(
                spoiler=self.spoiler,
                document=await self.file.to_tl_document(user),
            )
        elif self.type is MediaType.PHOTO:
            return MessageMediaPhoto(
                spoiler=self.spoiler,
                photo=await self.file.to_tl_photo(user),
            )
        elif self.type is MediaType.POLL:
            return MessageMediaPoll(
                poll=await self.poll.to_tl(),
                results=await self.poll.to_tl_results(user),
            )

        return MessageMediaUnsupported()
