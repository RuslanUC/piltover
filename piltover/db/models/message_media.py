from __future__ import annotations

from io import BytesIO

from loguru import logger
from tortoise import fields, Model

from piltover.db import models
from piltover.db.enums import MediaType, ChatBannedRights, FileType
from piltover.exceptions import InvalidConstructorException
from piltover.tl import MessageMediaUnsupported, MessageMediaPhoto, MessageMediaDocument, MessageMediaPoll, \
    MessageMediaContact, MessageMediaGeo, MessageMediaDice

MessageMediaTypes = MessageMediaUnsupported | MessageMediaPhoto | MessageMediaDocument | MessageMediaPoll \
                    | MessageMediaContact | MessageMediaGeo | MessageMediaDice


class MessageMedia(Model):
    id: int = fields.BigIntField(pk=True)
    spoiler: bool = fields.BooleanField(default=False)
    type: MediaType = fields.IntEnumField(MediaType, default=MediaType.DOCUMENT, description="")
    file: models.File | None = fields.ForeignKeyField("models.File", null=True, default=None)
    poll: models.Poll | None = fields.ForeignKeyField("models.Poll", null=True, default=None)
    static_data: bytes | None = fields.BinaryField(null=True, default=None)

    file_id: int | None
    poll_id: int | None

    def _to_tl_sync(self) -> MessageMediaTypes:
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
            raise ValueError("POLL media is not supported in _to_tl_sync")
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

    async def to_tl(self) -> MessageMediaTypes:
        if self.type is MediaType.POLL:
            # TODO: dont fetch if already fetched
            await self.fetch_related("poll", "poll__pollanswers")
            return MessageMediaPoll(
                poll=self.poll.to_tl(),
                results=await self.poll.to_tl_results(),
            )

        return self._to_tl_sync()

    @classmethod
    async def to_tl_bulk(cls, medias: list[MessageMedia]) -> list[MessageMediaTypes]:
        polls_to_refetch: dict[int, list[MessageMedia]] = {}
        for media in medias:
            if media.type != MediaType.POLL or media.poll.pollanswers._fetched:
                continue

            if media.poll.id not in polls_to_refetch:
                polls_to_refetch[media.poll.id] = []
            polls_to_refetch[media.poll.id].append(media)

        if polls_to_refetch:
            for poll in await models.Poll.filter(id__in=list(polls_to_refetch.keys())).prefetch_related("pollanswers"):
                for media in polls_to_refetch[poll.id]:
                    media.poll = poll

        polls = [media.poll for media in medias if media.type is MediaType.POLL]
        poll_results = {
            poll.id: results
            for poll, results in zip(polls, await models.Poll.to_tl_results_bulk(polls))
        }

        tl = []
        for media in medias:
            if media.type is MediaType.POLL:
                tl.append(MessageMediaPoll(
                    poll=media.poll.to_tl(),
                    results=poll_results[media.poll.id],
                ))
            else:
                tl.append(media._to_tl_sync())

        return tl

    def to_chat_banned_right(self) -> ChatBannedRights | None:
        media_type = self.type
        if media_type is MediaType.PHOTO:
            return ChatBannedRights.SEND_PHOTOS
        elif media_type is MediaType.POLL:
            return ChatBannedRights.SEND_POLLS
        elif media_type in (MediaType.DICE, MediaType.GEOPOINT, MediaType.CONTACT):
            return None
        elif media_type is MediaType.DOCUMENT and self.file is not None:
            return self.file.to_chat_banned_right()

        return ChatBannedRights.NONE
