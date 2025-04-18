from __future__ import annotations

from datetime import datetime
from io import BytesIO
from typing import Callable, Awaitable

from loguru import logger
from pytz import UTC
from tortoise import fields, Model
from tortoise.expressions import Q
from tortoise.functions import Count

from piltover.cache import Cache
from piltover.db import models
from piltover.db.enums import MessageType, PeerType, PrivacyRuleKeyType
from piltover.exceptions import Error, ErrorRpc
from piltover.tl import MessageReplyHeader, MessageService, PhotoEmpty, objects, Long, SerializationUtils, TLObject
from piltover.tl.types import Message as TLMessage, PeerUser, MessageActionChatEditPhoto, MessageActionChatAddUser, \
    MessageActionChatDeleteUser, MessageActionChatJoinedByRequest, MessageActionChatJoinedByLink, \
    MessageActionChatEditTitle, MessageActionChatCreate, MessageActionPinMessage, MessageReactions, ReactionCount, \
    ReactionEmoji
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


async def _service_chat_user_join_request(_1: Message, _2: models.User) -> MessageActionChatJoinedByRequest:
    return MessageActionChatJoinedByRequest()


MESSAGE_TYPE_TO_SERVICE_ACTION: dict[MessageType, Callable[[Message, models.User], Awaitable[...]]] = {
    MessageType.SERVICE_PIN_MESSAGE: _service_pin_message,
    MessageType.SERVICE_CHAT_CREATE: _service_create_chat,
    MessageType.SERVICE_CHAT_EDIT_TITLE: _service_edit_chat_title,
    MessageType.SERVICE_CHAT_EDIT_PHOTO: _service_edit_chat_photo,
    MessageType.SERVICE_CHAT_USER_ADD: _service_chat_add_user,
    MessageType.SERVICE_CHAT_USER_DEL: _service_chat_del_user,
    MessageType.SERVICE_CHAT_USER_INVITE_JOIN: _service_chat_user_join_invite,
    MessageType.SERVICE_CHAT_USER_REQUEST_JOIN: _service_chat_user_join_request,
}

_FWD_HEADER_MISSING = object()
_BASE_DEFAULTS = {
    "mentioned": False,
    "media_unread": False,
    "silent": False,
    "legacy": False,
}
_REGULAR_DEFAULTS = {
    "from_scheduled": False,
    "edit_hide": False,
    "noforwards": False,
    "restriction_reason": []
}


class Message(Model):
    id: int = fields.BigIntField(pk=True)
    internal_id: int = fields.BigIntField()
    message: str | None = fields.TextField(null=True, default=None)
    pinned: bool = fields.BooleanField(default=False)
    date: datetime = fields.DatetimeField(default=lambda: datetime.now(UTC))
    edit_date: datetime = fields.DatetimeField(null=True, default=None)
    type: MessageType = fields.IntEnumField(MessageType, default=MessageType.REGULAR)
    random_id: str = fields.CharField(max_length=24, null=True, default=None)
    entities: list[dict] | None = fields.JSONField(null=True, default=None)
    extra_info: bytes | None = fields.BinaryField(null=True, default=None)
    version: int = fields.IntField(default=0)
    media_group_id: int = fields.BigIntField(null=True, default=None)
    channel_post: bool = fields.BooleanField(default=False)
    post_author: str | None = fields.CharField(max_length=128, null=True, default=None)

    author: models.User = fields.ForeignKeyField("models.User", on_delete=fields.SET_NULL, null=True)
    peer: models.Peer = fields.ForeignKeyField("models.Peer")
    media: models.MessageMedia | None = fields.ForeignKeyField("models.MessageMedia", null=True, default=None)
    reply_to: models.Message | None = fields.ForeignKeyField("models.Message", null=True, default=None, on_delete=fields.SET_NULL)
    fwd_header: models.MessageFwdHeader | None = fields.ForeignKeyField("models.MessageFwdHeader", null=True, default=None)
    post_info: models.ChannelPostInfo | None = fields.ForeignKeyField("models.ChannelPostInfo", null=True, default=None)

    peer_id: int
    author_id: int | None
    media_id: int | None
    reply_to_id: int | None
    post_info_id: int | None

    class Meta:
        unique_together = (
            ("peer", "random_id"),
        )

    def _cache_key(self, user: models.User) -> str:
        return f"message:{user.id}:{self.id}:{self.version}"

    @classmethod
    async def get_(cls, id_: int, peer: models.Peer) -> models.Message | None:
        peer_query = Q(peer=peer)
        if peer.type is PeerType.CHANNEL:
            peer_query |= Q(peer__owner=None, peer__channel__id=peer.channel_id)
        return await Message.get_or_none(peer_query, id=id_, type=MessageType.REGULAR)\
            .select_related("peer", "author", "media")

    async def _make_reply_to_header(self) -> MessageReplyHeader:
        if self.reply_to is not None:
            self.reply_to = await self.reply_to
        return MessageReplyHeader(reply_to_msg_id=self.reply_to.id) if self.reply_to is not None else None

    async def _to_tl_service(self, user: models.User) -> MessageService:
        if self.type in (MessageType.SERVICE_CHAT_EDIT_PHOTO,):
            action = await MESSAGE_TYPE_TO_SERVICE_ACTION[self.type](self, user)
        else:
            try:
                # TODO: ensure type is one of message action types
                action = TLObject.read(BytesIO(self.extra_info))
            except Error:
                logger.debug(
                    f"Message {self.id} contains non-TL-encoded extra_info service message action, "
                    f"trying to migrate it..."
                )
                action = await MESSAGE_TYPE_TO_SERVICE_ACTION[self.type](self, user)
                self.extra_info = action.write()
                await self.save(update_fields=["extra_info"])

        from_id = None
        if not self.channel_post:
            from_id = PeerUser(user_id=self.author_id) if self.author_id else PeerUser(user_id=0)

        return MessageService(
            id=self.id,
            peer_id=self.peer.to_tl(),
            date=int(self.date.timestamp()),
            action=action,  # type: ignore
            out=user.id == self.author_id,
            reply_to=await self._make_reply_to_header(),
            from_id=from_id,
            **_BASE_DEFAULTS,
        )

    async def to_tl(self, current_user: models.User) -> TLMessage | MessageService:
        if (cached := await Cache.obj.get(self._cache_key(current_user))) is not None:
            if self.media_id is not None:
                file = await models.File.get_or_none(messagemedias__messages__id=self.id)
                if file is not None:
                    await models.FileAccess.get_or_renew(current_user, file, True)
            # TODO: reload reactions
            return cached

        if self.type is not MessageType.REGULAR:
            return await self._to_tl_service(current_user)

        media = None
        if self.media is not None:
            self.media = await self.media
            media = await self.media.to_tl(current_user) if self.media is not None else None

        if self.fwd_header is not None:
            self.fwd_header = await self.fwd_header

        entities = []
        for entity in (self.entities or []):
            tl_id = entity.pop("_")
            entities.append(objects[tl_id](**entity))

        from_id = None
        if not self.channel_post:
            from_id = PeerUser(user_id=self.author_id) if self.author_id else PeerUser(user_id=0)

        post_info = None
        if self.channel_post and self.post_info_id is not None:
            self.post_info = post_info = await self.post_info

        # TODO: reactions
        message = TLMessage(
            id=self.id,
            message=self.message or "",
            pinned=self.pinned,
            peer_id=self.peer.to_tl(),
            date=int(self.date.timestamp()),
            out=current_user.id == self.author_id,
            media=media,
            edit_date=int(self.edit_date.timestamp()) if self.edit_date is not None else None,
            reply_to=await self._make_reply_to_header(),
            fwd_from=await self.fwd_header.to_tl() if self.fwd_header is not None else None,
            from_id=from_id,
            entities=entities,
            grouped_id=self.media_group_id,
            post=self.channel_post,
            views=post_info.views if post_info is not None else None,
            forwards=post_info.forwards if post_info is not None else None,
            post_author=self.post_author if self.channel_post else None,
            **_BASE_DEFAULTS,
            **_REGULAR_DEFAULTS,
        )

        await Cache.obj.set(self._cache_key(current_user), message)
        return message

    async def clone_for_peer(
            self, peer: models.Peer, new_author: models.User | None = None, internal_id: int | None = None,
            random_id: int | None = None, fwd_header: models.MessageFwdHeader | None | object = _FWD_HEADER_MISSING,
            reply_to_internal_id: int | None = None, drop_captions: bool = False, media_group_id: int | None = None,
            drop_author: bool = False,
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

        if fwd_header is _FWD_HEADER_MISSING:
            self.fwd_header = fwd_header = await self.fwd_header
        if not drop_author:
            self.post_info = await self.post_info

        return await Message.create(
            internal_id=internal_id or Snowflake.make_id(),
            message=self.message if self.media is None or not drop_captions else None,
            pinned=self.pinned,
            date=self.date,
            edit_date=self.edit_date,
            type=self.type,
            author=new_author,
            peer=peer,
            media=self.media,
            reply_to=reply_to,
            fwd_header=fwd_header,
            random_id=str(random_id) if random_id else None,
            entities=self.entities,
            media_group_id=media_group_id,
            channel_post=self.channel_post if not drop_author else None,
            post_author=self.post_author if not drop_author else None,
            post_info=self.post_info if not drop_author else None,
        )

    async def create_fwd_header(self, peer: models.Peer) -> models.MessageFwdHeader | None:
        if self.fwd_header is not None:
            self.fwd_header = await self.fwd_header

        fwd_header = self.fwd_header
        self.author = await self.author
        if peer.type == PeerType.SELF and self.peer is not None:
            self.peer = await self.peer

        if fwd_header is not None:
            fwd_header.from_user = await fwd_header.from_user

        from_user = fwd_header.from_user if fwd_header else None
        if from_user is None and not self.channel_post:
            if await models.PrivacyRule.has_access_to(self.peer.owner_id, self.author, PrivacyRuleKeyType.FORWARDS):
                from_user = self.author

        saved_peer = self.peer if peer.type == PeerType.SELF else None
        if saved_peer is not None and peer.type is PeerType.USER:
            peer_ = self.peer
            if not await models.PrivacyRule.has_access_to(peer_.owner_id, peer_.user_id, PrivacyRuleKeyType.FORWARDS):
                saved_peer = None

        return await models.MessageFwdHeader.create(
            from_user=from_user,
            from_name=fwd_header.from_name if fwd_header else self.author.first_name,
            date=fwd_header.date if fwd_header else self.date,

            saved_peer=saved_peer,
            saved_id=self.id if peer.type == PeerType.SELF else None,
            saved_from=self.author if peer.type == PeerType.SELF else None,
            saved_name=self.author.first_name if peer.type == PeerType.SELF else None,
            saved_date=self.date if peer.type == PeerType.SELF else None,
        )

    @classmethod
    async def create_for_peer(
            cls, user: models.User, peer: models.Peer, random_id: int | None, reply_to_message_id: int | None,
            author: models.User, opposite: bool = True, **message_kwargs
    ) -> dict[models.Peer, Message]:
        from piltover.app.utils.updates_manager import UpdatesManager

        if random_id is not None and await Message.filter(peer=peer, random_id=str(random_id)).exists():
            raise ErrorRpc(error_code=500, error_message="RANDOM_ID_DUPLICATE")

        reply = None
        if reply_to_message_id:
            peer_filter = {"peer__channel": peer.channel} if peer.type is PeerType.CHANNEL else {"peer": peer}
            reply = await Message.get_or_none(id=reply_to_message_id, **peer_filter)
            if reply is None:
                raise ErrorRpc(error_code=400, error_message="REPLY_TO_INVALID")

        peers = [peer]
        if opposite and peer.type is not PeerType.CHANNEL:
            peers.extend(await peer.get_opposite())
        elif opposite and peer.type is PeerType.CHANNEL:
            peers = [await models.Peer.get_or_none(owner=None, channel=peer.channel, type=PeerType.CHANNEL)]
        messages: dict[models.Peer, Message] = {}

        internal_id = Snowflake.make_id()
        for to_peer in peers:
            await to_peer.fetch_related("owner", "user")
            await models.Dialog.get_or_create(peer=to_peer)
            if to_peer == peer and random_id is not None:
                message_kwargs["random_id"] = str(random_id)
            messages[to_peer] = await Message.create(
                internal_id=internal_id,
                peer=to_peer,
                reply_to=(await Message.get_or_none(peer=to_peer, internal_id=reply.internal_id)) if reply else None,
                author=author,
                **message_kwargs
            )
            message_kwargs.pop("random_id", None)

        presence = await models.Presence.update_to_now(user)
        await UpdatesManager.update_status(user, presence, peers[1:])

        return messages

    def query_users_chats(
            self, users: Q | None = None, chats: Q | None = None, channels: Q | None = None,
    ) -> tuple[Q | None, Q | None, Q | None]:
        if users is not None and self.author_id is not None and not self.channel_post:
            users |= Q(id=self.author_id)
        if (users is not None or chats is not None or channels is not None) and self.peer_id is not None:
            users, chats, channels = models.Peer.query_users_chats_cls(self.peer_id, users, chats, channels)
        if users is not None \
                and self.type in (MessageType.SERVICE_CHAT_USER_ADD, MessageType.SERVICE_CHAT_USER_DEL) \
                and self.extra_info:
            try:
                if self.type is MessageType.SERVICE_CHAT_USER_ADD:
                    user_ids = MessageActionChatAddUser.read(BytesIO(self.extra_info), True).users
                else:
                    user_ids = [MessageActionChatDeleteUser.read(BytesIO(self.extra_info), True).user_id]
            except Error:
                return users, chats, channels
            users |= Q(id__in=user_ids)

        # TODO: add users and chats from fwd_header

        return users, chats, channels

    async def remove_from_cache(self, user: models.User) -> None:
        await Cache.obj.delete(self._cache_key(user))

    async def to_tl_reactions(self, user: models.User) -> MessageReactions:
        # TODO: send min MessageReactions if current user didn't send reaction to message
        user_reaction = await models.MessageReaction.get_or_none(user=user, message=self)
        reactions = await models.MessageReaction\
            .annotate(msg_count=Count("id"))\
            .filter(message=self)\
            .group_by("reaction")\
            .select_related("reaction")\
            .values_list("reaction__id", "reaction__reaction", "msg_count")

        return MessageReactions(
            can_see_list=False,
            results=[
                ReactionCount(
                    chosen_order=1 if reaction_id == user_reaction.reaction_id else None,
                    reaction=ReactionEmoji(emoticon=reaction_emoji),
                    count=msg_count,
                )
                for reaction_id, reaction_emoji, msg_count in reactions
            ],
        )
