from __future__ import annotations

from datetime import datetime
from types import NoneType
from typing import Callable, Awaitable

from tortoise import fields, Model

from piltover.db import models
from piltover.db.enums import MediaType, MessageType
from piltover.tl import MessageMediaDocument, MessageMediaUnsupported, MessageMediaPhoto, MessageReplyHeader, \
    MessageService, PhotoEmpty
from piltover.tl.types import Message as TLMessage, MessageActionPinMessage, PeerUser, MessageActionChatCreate, \
    MessageActionChatEditTitle, MessageActionChatEditPhoto


async def _service_pin_message(_: Message, _u: models.User) -> MessageActionPinMessage:
    return MessageActionPinMessage()


async def _service_create_chat(message: Message, _: models.User) -> MessageActionChatCreate:
    await message.peer.fetch_related("chat")
    return MessageActionChatCreate(
        title=message.message if message.message is not None else message.peer.chat.name,
        users=[message.peer.chat.creator_id],
    )


async def _service_edit_chat_title(message: Message, _: models.User) -> MessageActionChatEditTitle:
    await message.peer.fetch_related("chat")
    return MessageActionChatEditTitle(
        title=message.message if message.message is not None else message.peer.chat.name,
    )


async def _service_edit_chat_photo(message: Message, user: models.User) -> MessageActionChatEditPhoto:
    try:
        photo_id = int(message.message)
    except ValueError:
        return MessageActionChatEditPhoto(photo=PhotoEmpty(id=0))

    await message.peer.fetch_related("chat")

    if photo_id > 0 and (file := await models.File.get_or_none(id=photo_id)) is not None:
        return MessageActionChatEditPhoto(photo=await file.to_tl_photo(user))

    return MessageActionChatEditPhoto(photo=PhotoEmpty(id=photo_id))


MESSAGE_TYPE_TO_SERVICE_ACTION: dict[MessageType, Callable[[Message, models.User], Awaitable[...]]] = {
    MessageType.SERVICE_PIN_MESSAGE: _service_pin_message,
    MessageType.SERVICE_CHAT_CREATE: _service_create_chat,
    MessageType.SERVICE_CHAT_EDIT_TITLE: _service_edit_chat_title,
    MessageType.SERVICE_CHAT_EDIT_PHOTO: _service_edit_chat_photo,
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

    async def to_tl(self, current_user: models.User) -> TLMessage | MessageService:
        # TODO: add some "version" field and save tl message in some cache with key f"{self.id}:{current_user.id}:{version}"

        base_defaults = {
            "mentioned": False,
            "media_unread": False,
            "silent": False,
            "post": False,
            "legacy": False,
        }

        from_id = PeerUser(user_id=self.author_id) if self.author_id else PeerUser(user_id=0)
        reply_to = await self._make_reply_to_header()

        if self.type is not MessageType.REGULAR:
            return MessageService(
                id=self.id,
                peer_id=self.peer.to_tl(),
                date=self.utime(),
                action=await MESSAGE_TYPE_TO_SERVICE_ACTION[self.type](self, current_user),
                out=current_user == self.author,
                reply_to=reply_to,
                from_id=from_id,
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
            from_id=from_id,
            **base_defaults,
            **regular_defaults,
        )
