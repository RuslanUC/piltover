from __future__ import annotations

from datetime import datetime

from tortoise import fields

from piltover.db import models
from piltover.db.enums import MediaType
from piltover.db.models._utils import Model
from piltover.tl import MessageMediaDocument, MessageMediaUnsupported, MessageMediaPhoto, MessageReplyHeader
from piltover.tl.types import Message as TLMessage


class Message(Model):
    id: int = fields.BigIntField(pk=True)
    message: str = fields.TextField()
    pinned: bool = fields.BooleanField(default=False)
    date: datetime = fields.DatetimeField(default=datetime.now)
    edit_date: datetime = fields.DatetimeField(null=True, default=None)

    author: models.User = fields.ForeignKeyField("models.User", on_delete=fields.SET_NULL, null=True)
    chat: models.Chat = fields.ForeignKeyField("models.Chat", on_delete=fields.CASCADE)
    reply_to: models.Message = fields.ForeignKeyField("models.Message", null=True, default=None,
                                                      on_delete=fields.SET_NULL)

    def utime(self) -> int:
        return int(self.date.timestamp())

    async def to_tl(self, current_user: models.User, **kwargs) -> TLMessage:
        # TODO: add some "version" field and save tl message in some cache with key f"{self.id}:{current_user.id}:{version}"

        defaults = {
            "mentioned": False,
            "media_unread": False,
            "silent": False,
            "post": False,
            "from_scheduled": False,
            "legacy": False,
            "edit_hide": False,
            "noforwards": False,
            "entities": [],
            "restriction_reason": []
        }

        tl_media = None
        if (media := await models.MessageMedia.get_or_none(message=self).select_related("file")) is not None:
            tl_media = MessageMediaUnsupported()
            if media.type == MediaType.DOCUMENT:
                tl_media = MessageMediaDocument(
                    spoiler=media.spoiler,
                    document=await media.file.to_tl_document(current_user)
                )
            elif media.type == MediaType.PHOTO:
                tl_media = MessageMediaPhoto(
                    spoiler=media.spoiler,
                    photo=await media.file.to_tl_photo(current_user)
                )

        await self.fetch_related("reply_to")
        reply_to = None
        if self.reply_to is not None:
            reply_to = MessageReplyHeader(reply_to_msg_id=self.reply_to.id, quote_entities=[])

        return TLMessage(
            id=self.id,
            message=self.message,
            pinned=self.pinned,
            peer_id=await self.chat.get_peer(current_user),
            date=self.utime(),
            out=current_user == self.author,
            media=tl_media,
            edit_date=int(self.edit_date.timestamp()) if self.edit_date is not None else None,
            reply_to=reply_to,
            **defaults
        )
