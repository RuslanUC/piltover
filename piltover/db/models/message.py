from __future__ import annotations

from datetime import datetime
from types import NoneType

from tortoise import fields

from piltover.db import models
from piltover.db.enums import MediaType, MessageType
from piltover.db.models._utils import Model
from piltover.tl import MessageMediaDocument, MessageMediaUnsupported, MessageMediaPhoto, MessageReplyHeader, \
    MessageService
from piltover.tl.types import Message as TLMessage, MessageActionPinMessage, PeerUser

MESSAGE_TYPE_TO_SERVICE_ACTION = {
    MessageType.SERVICE_PIN_MESSAGE: MessageActionPinMessage(),
}


class Message(Model):
    id: int = fields.BigIntField(pk=True)
    internal_id: int = fields.BigIntField()
    message: str = fields.TextField(null=True, default=None)
    pinned: bool = fields.BooleanField(default=False)
    date: datetime = fields.DatetimeField(default=datetime.now)
    edit_date: datetime = fields.DatetimeField(null=True, default=None)
    type: MessageType = fields.IntEnumField(MessageType, default=MessageType.REGULAR)
    random_id: str = fields.CharField(max_length=24, null=True, default=None)

    author: models.User = fields.ForeignKeyField("models.User", on_delete=fields.SET_NULL, null=True)
    peer: models.Peer = fields.ForeignKeyField("models.Peer")
    media: models.MessageMedia = fields.ForeignKeyField("models.MessageMedia", null=True, default=None)
    reply_to: models.Message = fields.ForeignKeyField("models.Message", null=True, default=None, on_delete=fields.SET_NULL)
    fwd_header: models.MessageFwdHeader = fields.ForeignKeyField("models.MessageFwdHeader", null=True, default=None)

    author_id: int

    class Meta:
        unique_together = (
            ("peer", "random_id"),
        )

    def utime(self) -> int:
        return int(self.date.timestamp())

    @classmethod
    async def get_(cls, id_: int, peer: models.Peer) -> models.Message | None:
        return await Message.get_or_none(id=id_, peer=peer, type=MessageType.REGULAR).select_related("peer", "author")

    async def _make_reply_to_header(self) -> MessageReplyHeader:
        if self.reply_to is not None:
            self.reply_to = await self.reply_to
        return MessageReplyHeader(reply_to_msg_id=self.reply_to.id) if self.reply_to is not None else None

    async def to_tl(self, current_user: models.User, **kwargs) -> TLMessage | MessageService:
        # TODO: add some "version" field and save tl message in some cache with key f"{self.id}:{current_user.id}:{version}"
        # TODO: from_id

        base_defaults = {
            "mentioned": False,
            "media_unread": False,
            "silent": False,
            "post": False,
            "legacy": False,
        }

        reply_to = await self._make_reply_to_header()

        if self.type is not MessageType.REGULAR:
            return MessageService(
                id=self.id,
                peer_id=self.peer.to_tl(),
                date=self.utime(),
                action=MESSAGE_TYPE_TO_SERVICE_ACTION[self.type],
                out=current_user == self.author,
                reply_to=reply_to,
                **base_defaults,
            )

        regular_defaults = {
            "from_scheduled": False,
            "edit_hide": False,
            "noforwards": False,
            "entities": [],
            "restriction_reason": []
        }

        tl_media = None
        if not isinstance(self.media, (models.MessageMedia, NoneType)):
            await self.fetch_related("media", "media__file")
        if self.media is not None:
            tl_media = MessageMediaUnsupported()
            if self.media.type == MediaType.DOCUMENT:
                tl_media = MessageMediaDocument(
                    spoiler=self.media.spoiler,
                    document=await self.media.file.to_tl_document(current_user),
                )
            elif self.media.type == MediaType.PHOTO:
                tl_media = MessageMediaPhoto(
                    spoiler=self.media.spoiler,
                    photo=await self.media.file.to_tl_photo(current_user),
                )

        if self.fwd_header is not None:
            self.fwd_header = await self.fwd_header

        return TLMessage(
            id=self.id,
            message=self.message,
            pinned=self.pinned,
            peer_id=self.peer.to_tl(),
            date=self.utime(),
            out=current_user == self.author,
            media=tl_media,
            edit_date=int(self.edit_date.timestamp()) if self.edit_date is not None else None,
            reply_to=reply_to,
            fwd_from=await self.fwd_header.to_tl() if self.fwd_header is not None else None,
            from_id=PeerUser(user_id=self.author_id) if self.author_id else PeerUser(user_id=0),
            **base_defaults,
            **regular_defaults,
        )
