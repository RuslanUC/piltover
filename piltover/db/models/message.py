from __future__ import annotations

from datetime import datetime
from enum import Enum, auto
from io import BytesIO
from typing import Callable, Awaitable, cast

from loguru import logger
from pytz import UTC
from tortoise import fields, Model
from tortoise.expressions import Q
from tortoise.functions import Count

from piltover.cache import Cache
from piltover.db import models
from piltover.db.enums import MessageType, PeerType, PrivacyRuleKeyType
from piltover.exceptions import Error, ErrorRpc
from piltover.tl import MessageReplyHeader, MessageService, PhotoEmpty, objects, Long, TLObject
from piltover.tl.base import MessageActionInst, MessageAction
from piltover.tl.base.internal import MessageActionNeedsProcessingInst, MessageActionNeedsProcessing
from piltover.tl.types import Message as TLMessage, PeerUser, MessageActionChatEditPhoto, MessageActionChatAddUser, \
    MessageActionChatDeleteUser, MessageReactions, ReactionCount, \
    ReactionEmoji, MessageMediaDocument, MessageMediaPhoto, MessageActionEmpty, WallPaperNoFile, \
    MessageActionSetChatWallPaper, MessageEntityMentionName
from piltover.tl.types.internal import MessageActionProcessSetChatWallpaper
from piltover.utils.snowflake import Snowflake


async def _service_edit_chat_photo(message: Message, user: models.User) -> MessageActionChatEditPhoto:
    if not message.extra_info:
        return MessageActionChatEditPhoto(photo=PhotoEmpty(id=0))

    photo_id = Long.read_bytes(message.extra_info)

    if photo_id > 0 and (file := await models.File.get_or_none(id=photo_id)) is not None:
        return MessageActionChatEditPhoto(photo=await file.to_tl_photo(user))

    return MessageActionChatEditPhoto(photo=PhotoEmpty(id=photo_id))


async def _process_service_message_action(
        action: MessageActionNeedsProcessing, _: Message, user: models.User,
) -> tuple[MessageAction, bool]:
    if isinstance(action, MessageActionProcessSetChatWallpaper):
        wallpaper = await models.Wallpaper.get_or_none(id=action.wallpaper_id).select_related("document", "settings")
        if wallpaper is not None:
            wallpaper_tl = await wallpaper.to_tl(user)
        else:
            wallpaper_tl = WallPaperNoFile(id=0)
        return MessageActionSetChatWallPaper(
            same=action.same,
            for_both=action.for_both,
            wallpaper=wallpaper_tl,
        ), False
    else:
        logger.warning(f"Got unknown message action to process: {action!r}")
        return MessageActionEmpty(), False


MESSAGE_TYPE_TO_SERVICE_ACTION: dict[MessageType, Callable[[Message, models.User], Awaitable[...]]] = {
    MessageType.SERVICE_CHAT_EDIT_PHOTO: _service_edit_chat_photo,
}


class _FwdHeaderMissing(Enum):
    FWD_HEADER_MISSING = auto()


_FWD_HEADER_MISSING = _FwdHeaderMissing.FWD_HEADER_MISSING
_BASE_DEFAULTS = {
    "silent": False,
    "legacy": False,
}
_REGULAR_DEFAULTS = {
    "edit_hide": False,
    "noforwards": False,
    "restriction_reason": [],
}
AllowedMessageActions = (*MessageActionInst, *MessageActionNeedsProcessingInst)


class Message(Model):
    id: int = fields.BigIntField(pk=True)
    internal_id: int = fields.BigIntField(index=True)
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
    scheduled_date: datetime | None = fields.DatetimeField(null=True, default=None)
    from_scheduled: bool = fields.BooleanField(default=False)

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
    async def get_(
            cls, id_: int, peer: models.Peer, types: tuple[MessageType, ...] = (MessageType.REGULAR,),
    ) -> models.Message | None:
        types_query = Q()
        for message_type in types:
            types_query |= Q(type=message_type)
        peer_query = Q(peer=peer)
        if peer.type is PeerType.CHANNEL:
            peer_query |= Q(peer__owner=None, peer__channel__id=peer.channel_id)
        return await Message.get_or_none(peer_query, types_query, id=id_)\
            .select_related("peer", "author", "media")

    @classmethod
    async def get_many(cls, ids: list[int], peer: models.Peer) -> list[models.Message]:
        peer_query = Q(peer=peer)
        if peer.type is PeerType.CHANNEL:
            peer_query |= Q(peer__owner=None, peer__channel__id=peer.channel_id)
        return await Message.filter(peer_query, id__in=ids, type=MessageType.REGULAR) \
            .select_related("peer", "author", "media")

    async def _make_reply_to_header(self) -> MessageReplyHeader:
        if self.reply_to is not None:
            self.reply_to = await self.reply_to
        return MessageReplyHeader(reply_to_msg_id=self.reply_to.id) if self.reply_to is not None else None

    # NOTE: keep in mind when implementing service messages caching:
    #  file references and access hashes must also be properly refreshed
    async def _to_tl_service(self, user: models.User) -> MessageService:
        if self.type in (MessageType.SERVICE_CHAT_EDIT_PHOTO,):
            action = await MESSAGE_TYPE_TO_SERVICE_ACTION[self.type](self, user)
        else:
            action = TLObject.read(BytesIO(self.extra_info))
            if not isinstance(action, AllowedMessageActions):
                logger.error(
                    f"Expected service message action to "
                    f"be any of this types: {AllowedMessageActions}, got {action=!r}"
                )
                action = MessageActionEmpty()

        if isinstance(action, MessageActionNeedsProcessingInst):
            logger.trace(f"Initial processing of message action {action!r}")
            action, save = await _process_service_message_action(action, self, user)
            if not isinstance(action, MessageActionEmpty) and save:
                logger.trace(f"Saving processed action: {action!r}")
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
            mentioned=False,
            media_unread=False,
        )

    async def to_tl(self, current_user: models.User, with_reactions: bool = False) -> TLMessage | MessageService:
        if (cached := await Cache.obj.get(self._cache_key(current_user))) is not None and not with_reactions:
            file_ref_obj = None
            if isinstance(cached.media, MessageMediaDocument):
                file_ref_obj = cached.media.document
            elif isinstance(cached.media, MessageMediaPhoto):
                file_ref_obj = cached.media.photo

            if self.media_id is not None \
                    and file_ref_obj is not None \
                    and not models.FileAccess.is_file_ref_valid(file_ref_obj.file_reference)[0]:
                file = await models.File.get_or_none(messagemedias__messages__id=self.id)
                if file is None:
                    return cached

                await current_user.load_if_lazy()

                access, _ = await models.FileAccess.get_or_create(file=file, user=current_user)
                file_ref_obj.file_reference = access.create_file_ref()

                await Cache.obj.set(self._cache_key(current_user), cached)

            return cached

        if self.type not in (MessageType.REGULAR, MessageType.SCHEDULED):
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
            entity["_"] = tl_id

        from_id = None
        if not self.channel_post:
            from_id = PeerUser(user_id=self.author_id) if self.author_id else PeerUser(user_id=0)

        post_info = None
        if self.channel_post and self.post_info_id is not None:
            self.post_info = post_info = await self.post_info

        mentioned = False
        mention_id = cast(
            int | None,
            await models.MessageMention.get_or_none(peer__owner=current_user, message=self).values_list("id", flat=True)
        )
        if mention_id is not None:
            # TODO: cache read state somewhere or pass as argument
            read_state, _ = await models.ReadState.get_or_create(peer=self.peer)
            mentioned = mention_id > read_state.last_mention_id

        media_unread = mentioned
        if not media_unread:
            ...  # TODO: check if media is read

        message = TLMessage(
            id=self.id,
            message=self.message or "",
            pinned=self.pinned,
            peer_id=self.peer.to_tl(),
            date=int((self.date if self.scheduled_date is None else self.scheduled_date).timestamp()),
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
            reactions=await self.to_tl_reactions(current_user) if with_reactions else None,
            mentioned=mentioned,
            media_unread=media_unread,
            from_scheduled=self.from_scheduled or self.scheduled_date is not None,
            **_BASE_DEFAULTS,
            **_REGULAR_DEFAULTS,
        )

        await Cache.obj.set(self._cache_key(current_user), message)
        return message

    async def send_scheduled(self, opposite: bool = True) -> dict[models.Peer, Message]:
        peers = [self.peer]
        if opposite and self.peer.type is not PeerType.CHANNEL:
            peers.extend(await self.peer.get_opposite())
        elif opposite and self.peer.type is PeerType.CHANNEL:
            peers = [await models.Peer.get_or_none(owner=None, channel__id=self.peer.channel_id, type=PeerType.CHANNEL)]

        messages: dict[models.Peer, Message] = {}

        for to_peer in peers:
            await to_peer.fetch_related("owner", "user")
            await models.Dialog.get_or_create(peer=to_peer)
            messages[to_peer] = await Message.create(
                from_scheduled=to_peer == self.peer,
                internal_id=self.internal_id,
                message=self.message,
                date=datetime.now(UTC),
                type=MessageType.REGULAR,
                author=self.author,
                peer=to_peer,
                media=self.media,
                reply_to=self.reply_to,
                fwd_header=self.fwd_header,
                entities=self.entities,
                media_group_id=self.media_group_id,
                channel_post=self.channel_post,
                post_author=self.post_author,
                post_info=self.post_info,
            )

        return messages

    async def clone_for_peer(
            self, peer: models.Peer, new_author: models.User | None = None, internal_id: int | None = None,
            random_id: int | None = None,
            fwd_header: models.MessageFwdHeader | None | _FwdHeaderMissing = _FWD_HEADER_MISSING,
            reply_to_internal_id: int | None = None, drop_captions: bool = False, media_group_id: int | None = None,
            drop_author: bool = False, is_forward: bool = False,
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
        if not drop_author and self.post_info is not None:
            self.post_info = await self.post_info

        return await Message.create(
            internal_id=internal_id or Snowflake.make_id(),
            message=self.message if self.media is None or not drop_captions else None,
            pinned=self.pinned,
            date=self.date if not is_forward else datetime.now(UTC),
            edit_date=self.edit_date if not is_forward else None,
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
        if peer.type is PeerType.SELF and self.peer is not None or True:
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
            cls, peer: models.Peer, random_id: int | None, reply_to_message_id: int | None,
            author: models.User, opposite: bool = True, **message_kwargs
    ) -> dict[models.Peer, Message]:
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
        if users is not None and self.entities:
            for entity in self.entities:
                if entity["_"] != MessageEntityMentionName.tlid():
                    continue
                users |= Q(id=entity["user_id"])

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
            .group_by("reaction__id")\
            .select_related("reaction")\
            .values_list("reaction__id", "reaction__reaction", "msg_count")

        # TODO: if `user.id == self.author_id`, always include unread reaction in recent_reactions

        return MessageReactions(
            can_see_list=False,
            results=[
                ReactionCount(
                    chosen_order=1 if user_reaction is not None and reaction_id == user_reaction.reaction_id else None,
                    reaction=ReactionEmoji(emoticon=reaction_emoji),
                    count=msg_count,
                )
                for reaction_id, reaction_emoji, msg_count in reactions
            ],
        )
