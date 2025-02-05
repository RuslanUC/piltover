from __future__ import annotations

from datetime import datetime
from io import BytesIO
from types import NoneType
from typing import Callable, Awaitable

from tortoise import fields, Model

from piltover.cache import Cache
from piltover.db import models
from piltover.db.enums import MediaType, MessageType, PeerType, PrivacyRuleKeyType
from piltover.tl import MessageMediaDocument, MessageMediaUnsupported, MessageMediaPhoto, MessageReplyHeader, \
    MessageService, PhotoEmpty, User as TLUser, Chat as TLChat, objects, SerializationUtils, Long
from piltover.tl.types import Message as TLMessage, MessageActionPinMessage, PeerUser, MessageActionChatCreate, \
    MessageActionChatEditTitle, MessageActionChatEditPhoto, MessageActionChatAddUser, MessageActionChatDeleteUser, \
    MessageActionChatJoinedByLink
from piltover.utils.snowflake import Snowflake


async def _service_pin_message(_: Message, _u: models.User) -> MessageActionPinMessage:
    return MessageActionPinMessage()


async def _service_create_chat(message: Message, _: models.User) -> MessageActionChatCreate:
    if not message.extra_info:
        return MessageActionChatCreate(title="", users=[])

    stream = BytesIO(message.extra_info)
    title = SerializationUtils.read(stream, str)
    user_ids = SerializationUtils.read(stream, list, Long)
    return MessageActionChatCreate(title=title, users=user_ids)


async def _service_edit_chat_title(message: Message, _: models.User) -> MessageActionChatEditTitle:
    if not message.extra_info:
        return MessageActionChatEditTitle(title="")

    return MessageActionChatEditTitle(
        title=SerializationUtils.read(BytesIO(message.extra_info), str),
    )


async def _service_edit_chat_photo(message: Message, user: models.User) -> MessageActionChatEditPhoto:
    if not message.extra_info:
        return MessageActionChatEditPhoto(photo=PhotoEmpty(id=0))

    photo_id = Long.read_bytes(message.extra_info)

    if photo_id > 0 and (file := await models.File.get_or_none(id=photo_id)) is not None:
        return MessageActionChatEditPhoto(photo=await file.to_tl_photo(user))

    return MessageActionChatEditPhoto(photo=PhotoEmpty(id=photo_id))


async def _service_chat_add_user(message: Message, _: models.User) -> MessageActionChatAddUser:
    if not message.extra_info:
        return MessageActionChatAddUser(users=[])

    user_ids = SerializationUtils.read(BytesIO(message.extra_info), list, Long)
    return MessageActionChatAddUser(users=user_ids)


async def _service_chat_del_user(message: Message, _: models.User) -> MessageActionChatDeleteUser:
    if not message.extra_info:
        return MessageActionChatDeleteUser(user_id=0)

    return MessageActionChatDeleteUser(user_id=Long.read_bytes(message.extra_info))


async def _service_chat_user_join_invite(message: Message, _: models.User) -> MessageActionChatJoinedByLink:
    if not message.extra_info:
        return MessageActionChatJoinedByLink(inviter_id=0)

    return MessageActionChatJoinedByLink(inviter_id=Long.read_bytes(message.extra_info))


MESSAGE_TYPE_TO_SERVICE_ACTION: dict[MessageType, Callable[[Message, models.User], Awaitable[...]]] = {
    MessageType.SERVICE_PIN_MESSAGE: _service_pin_message,
    MessageType.SERVICE_CHAT_CREATE: _service_create_chat,
    MessageType.SERVICE_CHAT_EDIT_TITLE: _service_edit_chat_title,
    MessageType.SERVICE_CHAT_EDIT_PHOTO: _service_edit_chat_photo,
    MessageType.SERVICE_CHAT_USER_ADD: _service_chat_add_user,
    MessageType.SERVICE_CHAT_USER_DEL: _service_chat_del_user,
    MessageType.SERVICE_CHAT_USER_INVITE_JOIN: _service_chat_user_join_invite,
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
    entities: list[dict] | None = fields.JSONField(null=True, default=None)
    extra_info: bytes | None = fields.BinaryField(null=True, default=None)
    version: int = fields.IntField(default=0)
    media_group_id: int = fields.BigIntField(null=True, default=None)

    author: models.User = fields.ForeignKeyField("models.User", on_delete=fields.SET_NULL, null=True)
    peer: models.Peer = fields.ForeignKeyField("models.Peer")
    media: models.MessageMedia = fields.ForeignKeyField("models.MessageMedia", null=True, default=None)
    reply_to: models.Message = fields.ForeignKeyField("models.Message", null=True, default=None, on_delete=fields.SET_NULL)
    fwd_header: models.MessageFwdHeader = fields.ForeignKeyField("models.MessageFwdHeader", null=True, default=None)

    author_id: int
    media_id: int | None

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
        if (cached := await Cache.obj.get(f"message:{self.id}:{self.version}")) is not None:
            if self.media_id is not None:
                file = await models.File.get_or_none(messagemedias__messages__id=self.id)
                if file is not None:
                    await models.FileAccess.get_or_renew(current_user, file, True)
            return cached

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
            "restriction_reason": []
        }

        tl_media = None
        if not isinstance(self.media, (models.MessageMedia, NoneType)):
            await self.fetch_related("media", "media__file")
        if self.media is not None:
            tl_media = await self.media.to_tl(current_user)

        if self.fwd_header is not None:
            self.fwd_header = await self.fwd_header

        entities = []
        for entity in (self.entities or []):
            tl_id = entity.pop("_")
            entities.append(objects[tl_id](**entity))

        message = TLMessage(
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
            entities=entities,
            grouped_id=self.media_group_id,
            **base_defaults,
            **regular_defaults,
        )

        await Cache.obj.set(f"message:{self.id}:{self.version}", message)
        return message

    async def clone_for_peer(
            self, peer: models.Peer, new_author: models.User | None = None, internal_id: int | None = None,
            random_id: int | None = None, fwd: bool = False, fwd_drop_header: bool = False,
            reply_to_internal_id: int | None = None, fwd_drop_captions: bool = False, media_group_id: int | None = None,
    ) -> models.Message:
        if new_author is None and self.author is not None:
            self.author = new_author = await self.author

        if self.media_id is not None:
            self.media = await self.media

        reply_to = None
        if reply_to_internal_id:
            reply_to = await Message.get_or_none(peer=peer, internal_id=reply_to_internal_id)
        else:
            if self.reply_to is not None:
                self.reply_to = await self.reply_to
            if self.reply_to is not None:
                reply_to = await Message.get_or_none(peer=peer, internal_id=self.reply_to.internal_id)

        if self.fwd_header is not None:
            self.fwd_header = await self.fwd_header
        fwd_header = None
        if fwd and not fwd_drop_header:
            fwd_header = self.fwd_header
            self.author = await self.author
            if peer.type == PeerType.SELF and self.peer is not None:
                self.peer = await self.peer

            if fwd_header is not None:
                fwd_header.from_user = await fwd_header.from_user

            from_user = fwd_header.from_user if fwd_header else None
            if from_user is None:
                await self.peer.fetch_related("owner")
                if await models.PrivacyRule.has_access_to(self.peer.owner, self.author, PrivacyRuleKeyType.FORWARDS):
                    from_user = self.author

            saved_peer = self.peer if peer.type == PeerType.SELF else None
            if saved_peer is not None and peer.type is PeerType.USER:
                await self.peer.fetch_related("owner", "user")
                peer_ = self.peer
                if not await models.PrivacyRule.has_access_to(peer_.owner, peer_.user, PrivacyRuleKeyType.FORWARDS):
                    saved_peer = None

            fwd_header = await models.MessageFwdHeader.create(
                from_user=from_user,
                from_name=fwd_header.from_name if fwd_header else self.author.first_name,
                date=fwd_header.date if fwd_header else self.date,

                saved_peer=saved_peer,
                saved_id=self.id if peer.type == PeerType.SELF else None,
                saved_from=self.author if peer.type == PeerType.SELF else None,
                saved_name=self.author.first_name if peer.type == PeerType.SELF else None,
                saved_date=self.date if peer.type == PeerType.SELF else None,
            )

        return await Message.create(
            internal_id=internal_id or Snowflake.make_id(),
            message=self.message if self.media is None or not fwd_drop_captions else None,
            pinned=self.pinned,
            date=self.date,
            edit_date=self.edit_date,
            type=self.type,
            author=new_author,
            peer=peer,
            media=self.media,
            reply_to=reply_to,
            fwd_header=fwd_header if not fwd_drop_header else None,
            random_id=str(random_id) if random_id else None,
            entities=self.entities,
            media_group_id=media_group_id,
        )

    async def tl_users_chats(
            self, user: models.User, users: dict[int, TLUser] | None = None, chats: dict[int, TLChat] | None = None,
    ) -> tuple[dict[int, TLUser] | None, dict[int, TLChat] | None]:
        if users is not None and self.author is not None and self.author_id not in users:
            self.author = await self.author
            users[self.author.id] = await self.author.to_tl(user)

        if (users is not None or chats is not None) and self.peer is not None:
            self.peer = await self.peer
            await self.peer.tl_users_chats(user, users, chats)

        if users is not None \
                and self.type in (MessageType.SERVICE_CHAT_USER_ADD, MessageType.SERVICE_CHAT_USER_DEL) \
                and self.extra_info:
            if self.type is MessageType.SERVICE_CHAT_USER_ADD:
                user_ids = SerializationUtils.read(BytesIO(self.extra_info), list, Long)
            else:
                user_ids = [Long.read_bytes(self.extra_info)]
            for user_id in user_ids:
                if user_id not in users and (participant := await models.User.get_or_none(id=user_id)) is not None:
                    users[participant.id] = await participant.to_tl(user)

        return users, chats
