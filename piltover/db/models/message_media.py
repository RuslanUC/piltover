from __future__ import annotations

from io import BytesIO

from loguru import logger
from tortoise import fields, Model

from piltover.db import models
from piltover.db.enums import MediaType
from piltover.exceptions import InvalidConstructorException
from piltover.tl import MessageMediaUnsupported, MessageMediaPhoto, MessageMediaDocument, MessageMediaPoll, \
    MessageMediaContact, MessageMediaGeo, MessageMediaDice

MessageMediaTypes = MessageMediaUnsupported | MessageMediaPhoto | MessageMediaDocument | MessageMediaPoll \
                    | MessageMediaContact | MessageMediaGeo | MessageMediaDice


class MessageMedia(Model):
    id: int = fields.BigIntField(pk=True)
    spoiler: bool = fields.BooleanField(default=False)
    type: MediaType = fields.IntEnumField(MediaType, default=MediaType.DOCUMENT)
    file: models.File | None = fields.ForeignKeyField("models.File", null=True, default=None)
    poll: models.Poll | None = fields.ForeignKeyField("models.Poll", null=True, default=None)
    static_data: bytes | None = fields.BinaryField(null=True, default=None)
    version: int = fields.IntField(default=0)

    file_id: int | None
    poll_id: int | None

    async def to_tl(self, user: models.User | int) -> MessageMediaTypes:
        user_id = user.id if isinstance(user, models.User) else user

        if self.type is MediaType.DOCUMENT:
            return MessageMediaDocument(
                spoiler=self.spoiler,
                document=self.file.to_tl_document(),
            )
        elif self.type is MediaType.PHOTO:
            return MessageMediaPhoto(
                spoiler=self.spoiler,
                photo=self.file.to_tl_photo(),
            )
        elif self.type is MediaType.POLL:
            await self.fetch_related("poll", "poll__pollanswers")
            return MessageMediaPoll(
                poll=self.poll.to_tl(),
                # TODO: replace with PollResultsToFormat or something
                results=await self.poll.to_tl_results(user_id),
            )
        elif self.type is MediaType.CONTACT:
            if self.static_data is None:
                logger.warning("Expected \"static_data\" to be non-null for contact media type")
                return MessageMediaUnsupported()
            try:
                contact = MessageMediaContact.read(BytesIO(self.static_data))
            except InvalidConstructorException as e:
                logger.opt(exception=e).warning("Invalid \"static_data\" data for contact media type")
                return MessageMediaUnsupported()

            return contact
        elif self.type is MediaType.GEOPOINT:
            if self.static_data is None:
                logger.warning("Expected \"static_data\" to be non-null for geo media type")
                return MessageMediaUnsupported()
            try:
                geo = MessageMediaGeo.read(BytesIO(self.static_data))
            except InvalidConstructorException as e:
                logger.opt(exception=e).warning("Invalid \"static_data\" data for geo media type")
                return MessageMediaUnsupported()

            return geo
        elif self.type is MediaType.DICE:
            if self.static_data is None:
                logger.warning("Expected \"static_data\" to be non-null for dice media type")
                return MessageMediaUnsupported()
            try:
                dice = MessageMediaDice.read(BytesIO(self.static_data))
            except InvalidConstructorException as e:
                logger.opt(exception=e).warning("Invalid \"static_data\" data for dice media type")
                return MessageMediaUnsupported()

            return dice

        return MessageMediaUnsupported()
