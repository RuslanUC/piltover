from __future__ import annotations

from datetime import datetime
from enum import Enum, auto
from io import BytesIO
from os import environ
from typing import cast, Iterable

from loguru import logger
from pytz import UTC
from tortoise import fields, Model
from tortoise.expressions import Q
from tortoise.functions import Count

from piltover.cache import Cache
from piltover.db import models
from piltover.db.enums import MessageType, PeerType, PrivacyRuleKeyType
from piltover.exceptions import ErrorRpc, Unreachable, Error
from piltover.tl import MessageReplyHeader, objects, TLObject
from piltover.tl.base import MessageActionInst, ReplyMarkupInst, ReplyMarkup, Message as TLMessageBase
from piltover.tl.to_format import MessageServiceToFormat
from piltover.tl.types import Message as TLMessage, PeerUser, MessageActionChatAddUser, \
    MessageActionChatDeleteUser, MessageReactions, ReactionCount, ReactionEmoji, MessageActionEmpty, \
    MessageEntityMentionName
from piltover.utils.snowflake import Snowflake


class _SomethingMissing(Enum):
    MISSING = auto()


_SMTH_MISSING = _SomethingMissing.MISSING


async def append_channel_min_message_id_to_query_maybe(
        peer: models.Peer, query: Q, participant: models.ChatParticipant | None = None,
) -> Q:
    if isinstance(peer, models.Peer) and peer.type is PeerType.CHANNEL:
        if participant is None:
            participant = await models.ChatParticipant.get_or_none(channel=peer.channel, user=peer.owner)
        if (channel_min_id := peer.channel.min_id(participant)) is not None:
            query &= Q(id__gte=channel_min_id)
    return query


class Message(Model):
    id: int = fields.BigIntField(pk=True)
    internal_id: int = fields.BigIntField(index=True)
    message: str | None = fields.TextField(null=True, default=None)
    pinned: bool = fields.BooleanField(default=False)
    date: datetime = fields.DatetimeField(default=lambda: datetime.now(UTC))
    edit_date: datetime = fields.DatetimeField(null=True, default=None)
    type: MessageType = fields.IntEnumField(MessageType, default=MessageType.REGULAR)
    random_id: str = fields.CharField(max_length=24, null=True, default=None)
    # TODO: use tl for entities
    entities: list[dict] | None = fields.JSONField(null=True, default=None)
    extra_info: bytes | None = fields.BinaryField(null=True, default=None)
    version: int = fields.IntField(default=0)
    media_group_id: int = fields.BigIntField(null=True, default=None)
    channel_post: bool = fields.BooleanField(default=False)
    post_author: str | None = fields.CharField(max_length=128, null=True, default=None)
    scheduled_date: datetime | None = fields.DatetimeField(null=True, default=None)
    from_scheduled: bool = fields.BooleanField(default=False)
    ttl_period_days: int | None = fields.SmallIntField(null=True, default=None)
    # TODO: create fields type for tl objects
    reply_markup: bytes | None = fields.BinaryField(null=True, default=None)
    no_forwards: bool = fields.BooleanField(default=False)

    author: models.User = fields.ForeignKeyField("models.User", on_delete=fields.SET_NULL, null=True)
    peer: models.Peer = fields.ForeignKeyField("models.Peer")
    # TODO: "file__stickerset" should be prefetched with media
    media: models.MessageMedia | None = fields.ForeignKeyField("models.MessageMedia", null=True, default=None)
    reply_to: models.Message | None = fields.ForeignKeyField("models.Message", null=True, default=None, on_delete=fields.SET_NULL)
    fwd_header: models.MessageFwdHeader | None = fields.ForeignKeyField("models.MessageFwdHeader", null=True, default=None)
    post_info: models.ChannelPostInfo | None = fields.ForeignKeyField("models.ChannelPostInfo", null=True, default=None)
    via_bot: models.User | None = fields.ForeignKeyField("models.User", on_delete=fields.SET_NULL, null=True, default=None, related_name="msg_via_bot")

    peer_id: int
    author_id: int | None
    media_id: int | None
    reply_to_id: int | None
    fwd_header_id: int | None
    post_info_id: int | None
    via_bot_id: int | None

    TTL_MULT = 86400
    if (_ttl_mult := environ.get("DEBUG_MESSAGE_TTL_MULTIPLIER", "")).isdigit():
        TTL_MULT = int(_ttl_mult)

    _cached_reply_markup: ReplyMarkup | None | _SomethingMissing = _SMTH_MISSING

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

        query = peer_query & types_query & Q(id=id_)
        query = await append_channel_min_message_id_to_query_maybe(peer, query)

        return await Message.get_or_none(query).select_related("peer", "author", "media")

    @classmethod
    async def get_many(cls, ids: list[int], peer: models.Peer) -> list[models.Message]:
        peer_query = Q(peer=peer)
        if peer.type is PeerType.CHANNEL:
            peer_query |= Q(peer__owner=None, peer__channel__id=peer.channel_id)

        query = peer_query & Q(id__in=ids, type=MessageType.REGULAR)
        query = await append_channel_min_message_id_to_query_maybe(peer, query)

        return await Message.filter(query).select_related("peer", "author", "media")

    def _make_reply_to_header(self) -> MessageReplyHeader:
        return MessageReplyHeader(reply_to_msg_id=self.reply_to_id) if self.reply_to_id is not None else None

    def _to_tl_service(self) -> MessageServiceToFormat:
        action = TLObject.read(BytesIO(self.extra_info))
        if not isinstance(action, MessageActionInst):
            logger.error(
                f"Expected service message action to "
                f"be any of this types: {MessageActionInst}, got {action=!r}"
            )
            action = MessageActionEmpty()

        # NOTE: this is first step to making messages cachable for not-defined amount of time for all users.
        #  But we need to keep in mind that:
        #   1. Messages should be cached based on `internal_id` not actual message `id`
        #    (or whole id system should be reworked and rewritten).
        #   2. Fields such as `peer_id` or `reply_to` are NOT cachable based in internal id in private chats:
        #    `peer_id` can be specified as PeerPrivate(user1_id=..., user2_id=...),
        #    but `reply_to` is unknown for user users for private chats in this method.
        return MessageServiceToFormat(
            id=self.id,
            peer_id=self.peer.to_tl(),
            date=int(self.date.timestamp()),
            action=action,
            author_id=self.author_id,
            reply_to=self._make_reply_to_header(),
            from_id=PeerUser(user_id=self.author_id) if not self.channel_post else None,
            ttl_period=self.ttl_period_days * self.TTL_MULT if self.ttl_period_days else None,
        )

    async def to_tl(self, current_user: models.User, with_reactions: bool = False) -> TLMessageBase:
        if (cached := await Cache.obj.get(self._cache_key(current_user))) is not None and not with_reactions:
            return cached

        if self.type not in (MessageType.REGULAR, MessageType.SCHEDULED):
            return self._to_tl_service()

        media = None
        if self.media is not None:
            await self.fetch_related("media", "media__file", "media__file__stickerset")
            media = await self.media.to_tl(current_user) if self.media is not None else None

        if self.fwd_header is not None:
            self.fwd_header = await self.fwd_header

        entities = []
        for entity in (self.entities or []):
            tl_id = entity.pop("_")
            entities.append(objects[tl_id](**entity))
            entity["_"] = tl_id

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
            # read_state, _ = await models.ReadState.get_or_create(peer=self.peer)
            mentioned = True  # mention_id > read_state.last_mention_id

        media_unread = mentioned
        if not media_unread:
            ...  # TODO: check if media is read

        ttl_period = None
        if self.ttl_period_days and self.type is MessageType.REGULAR:
            ttl_period = self.ttl_period_days * self.TTL_MULT

        reply_markup = self.make_reply_markup()

        message = TLMessage(
            id=self.id,
            message=self.message or "",
            pinned=self.pinned,
            peer_id=self.peer.to_tl(),
            date=int((self.date if self.scheduled_date is None else self.scheduled_date).timestamp()),
            out=current_user.id == self.author_id,
            media=media,
            edit_date=int(self.edit_date.timestamp()) if self.edit_date is not None else None,
            reply_to=self._make_reply_to_header(),
            fwd_from=await self.fwd_header.to_tl() if self.fwd_header is not None else None,
            from_id=PeerUser(user_id=self.author_id) if not self.channel_post else None,
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
            ttl_period=ttl_period,
            reply_markup=reply_markup,
            noforwards=self.no_forwards,
            via_bot_id=self.via_bot_id,

            silent=False,
            legacy=False,
            edit_hide=False,
            restriction_reason=[],
        )

        await Cache.obj.set(self._cache_key(current_user), message)
        return message

    def make_reply_markup(self) -> ReplyMarkup | None:
        if self._cached_reply_markup is _SMTH_MISSING:
            if self.reply_markup is None:
                self._cached_reply_markup = None
            else:
                reply_markup = TLObject.read(BytesIO(self.reply_markup))
                if not isinstance(reply_markup, ReplyMarkupInst):
                    logger.error(
                        f"Expected reply markup to be any of this types: {ReplyMarkupInst}, got {reply_markup=!r}"
                    )
                    reply_markup = None
                self._cached_reply_markup = reply_markup

        return self._cached_reply_markup

    def invalidate_reply_markup_cache(self) -> None:
        self._cached_reply_markup = _SMTH_MISSING

    async def send_scheduled(self, opposite: bool = True) -> dict[models.Peer, Message]:
        peers = [self.peer]
        if opposite and self.peer.type is not PeerType.CHANNEL:
            peers.extend(await self.peer.get_opposite())
        elif opposite and self.peer.type is PeerType.CHANNEL:
            peers = [await models.Peer.get_or_none(owner=None, channel__id=self.peer.channel_id, type=PeerType.CHANNEL)]

        messages: dict[models.Peer, Message] = {}

        send_date = datetime.now(UTC)
        for to_peer in peers:
            await to_peer.fetch_related("owner", "user")
            await models.Dialog.create_or_unhide(to_peer)
            messages[to_peer] = await Message.create(
                from_scheduled=to_peer == self.peer,
                internal_id=self.internal_id,
                message=self.message,
                date=send_date,
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
                ttl_period_days=self.ttl_period_days,
            )

        related_users, related_chats, related_channels = await models.MessageRelated.get_for_message(self)
        await self._create_related(messages.values(), related_users, related_chats, related_channels)

        return messages

    async def clone_for_peer(
            self, peer: models.Peer, new_author: models.User | None = None, internal_id: int | None = None,
            random_id: int | None = None,
            fwd_header: models.MessageFwdHeader | None | _SomethingMissing = _SMTH_MISSING,
            reply_to_internal_id: int | None = None, drop_captions: bool = False, media_group_id: int | None = None,
            drop_author: bool = False, is_forward: bool = False, no_forwards: bool = False,
    ) -> models.Message:
        await self.fetch_related("author", "media", "reply_to", "fwd_header", "post_info", "via_bot")

        if new_author is None and self.author is not None:
            new_author = self.author

        reply_to = None
        if reply_to_internal_id:
            reply_to = await Message.get_or_none(peer=peer, internal_id=reply_to_internal_id)
        else:
            if self.reply_to is not None:
                reply_to = await Message.get_or_none(peer=peer, internal_id=self.reply_to.internal_id)

        if fwd_header is _SMTH_MISSING:
            fwd_header = await self.fwd_header

        message = await Message.create(
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
            no_forwards=no_forwards,
            via_bot=self.via_bot,
        )

        related_user_ids = set()
        related_chat_ids = set()
        related_channel_ids = set()
        message._fill_related(related_user_ids, related_chat_ids, related_channel_ids)
        await self._create_related_from_ids((message,), related_user_ids, related_chat_ids, related_channel_ids)

        return message

    async def create_fwd_header(self, peer: models.Peer) -> models.MessageFwdHeader | None:
        if self.fwd_header is not None:
            from_user = self.fwd_header.from_user
            from_chat = self.fwd_header.from_chat
            from_channel = self.fwd_header.from_channel
            from_name = self.fwd_header.from_name
            channel_post_id = self.fwd_header.channel_post_id
            channel_post_author = self.fwd_header.channel_post_author
        else:
            from_user = None
            from_chat = None
            from_channel = None
            channel_post_id = None
            channel_post_author = None
            if self.channel_post:
                from_channel = self.peer.channel
                from_name = from_channel.name
                channel_post_id = self.id
                channel_post_author = self.post_author
            else:
                # TODO: handle anonymous admins in chats and channels
                if await models.PrivacyRule.has_access_to(self.peer.owner_id, self.author, PrivacyRuleKeyType.FORWARDS):
                    from_user = self.author
                from_name = self.author.first_name

        saved_peer = self.peer if peer.type == PeerType.SELF else None
        if saved_peer is not None and peer.type is PeerType.USER:
            peer_ = self.peer
            if not await models.PrivacyRule.has_access_to(peer_.owner_id, peer_.user_id, PrivacyRuleKeyType.FORWARDS):
                saved_peer = None

        return await models.MessageFwdHeader.create(
            from_user=from_user,
            from_chat=from_chat,
            from_channel=from_channel,
            from_name=from_name,
            date=self.fwd_header.date if self.fwd_header else self.date,

            channel_post_id=channel_post_id,
            channel_post_author=channel_post_author,

            saved_peer=saved_peer,
            saved_id=self.id if peer.type == PeerType.SELF else None,
            saved_from=self.author if peer.type == PeerType.SELF else None,
            saved_name=self.author.first_name if peer.type == PeerType.SELF else None,
            saved_date=self.date if peer.type == PeerType.SELF else None,
        )

    @classmethod
    async def create_for_peer(
            cls, peer: models.Peer, random_id: int | None, reply_to_message_id: int | None,
            author: models.User, opposite: bool = True, unhide_dialog: bool = True, **message_kwargs
    ) -> dict[models.Peer, Message]:
        if random_id is not None and await Message.filter(peer=peer, random_id=str(random_id)).exists():
            raise ErrorRpc(error_code=500, error_message="RANDOM_ID_DUPLICATE")

        reply = None
        if reply_to_message_id:
            if peer.type is PeerType.CHANNEL:
                peer_filter = {"peer__channel": peer.channel, "peer__owner": None}
            else:
                peer_filter = {"peer": peer}
            reply = await Message.get_or_none(id=reply_to_message_id, **peer_filter)
            if reply is None:
                raise ErrorRpc(error_code=400, error_message="REPLY_TO_INVALID")

        peers = [peer]
        if opposite and peer.type is not PeerType.CHANNEL:
            peers.extend(await peer.get_opposite())
        elif opposite and peer.type is PeerType.CHANNEL:
            peers = [await models.Peer.get_or_none(owner=None, channel=peer.channel, type=PeerType.CHANNEL)]
        messages: dict[models.Peer, Message] = {}

        related_user_ids: set[int] = set()
        related_chat_ids: set[int] = set()
        related_channel_ids: set[int] = set()

        internal_id = Snowflake.make_id()
        for to_peer in peers:
            await to_peer.fetch_related("owner", "user")
            if unhide_dialog:
                await models.Dialog.create_or_unhide(to_peer)
            if to_peer == peer and random_id is not None:
                message_kwargs["random_id"] = str(random_id)
            messages[to_peer] = message = await Message.create(
                internal_id=internal_id,
                peer=to_peer,
                reply_to=(await Message.get_or_none(peer=to_peer, internal_id=reply.internal_id)) if reply else None,
                author=author,
                **message_kwargs
            )
            message_kwargs.pop("random_id", None)
            message._fill_related(related_user_ids, related_chat_ids, related_channel_ids)

        await cls._create_related_from_ids(messages.values(), related_user_ids, related_chat_ids, related_channel_ids)

        return messages

    @staticmethod
    def _fill_related_peer(peer: models.Peer, user_ids: set[int], chat_ids: set[int], channel_ids: set[int]) -> None:
        if peer.user_id is not None:
            user_ids.add(peer.user_id)
        if peer.owner_id is not None:
            user_ids.add(peer.owner_id)
        if peer.chat_id is not None:
            chat_ids.add(peer.chat_id)
        if peer.channel_id is not None:
            channel_ids.add(peer.channel_id)

    def _fill_related(
            self, user_ids: set[int], chat_ids: set[int], channel_ids: set[int],
    ) -> None:
        self._fill_related_peer(self.peer, user_ids, chat_ids, channel_ids)

        if not self.channel_post and self.author_id is not None:
            user_ids.add(self.author_id)

        if self.type is MessageType.SERVICE_CHAT_USER_ADD:
            data = MessageActionChatAddUser.read(BytesIO(self.extra_info))
            user_ids.update(data.users)
        elif self.type is MessageType.SERVICE_CHAT_USER_DEL:
            data = MessageActionChatDeleteUser.read(BytesIO(self.extra_info))
            user_ids.add(data.user_id)

        # TODO: SERVICE_CHAT_MIGRATE_FROM / SERVICE_CHAT_MIGRATE_TO ?

        if self.entities:
            for entity in self.entities:
                if entity["_"] != MessageEntityMentionName.tlid():
                    continue
                user_ids.add(entity["user_id"])

        if self.fwd_header_id is not None:
            if self.fwd_header.from_user_id is not None:
                user_ids.add(self.fwd_header.from_user_id)
            if self.fwd_header.from_chat_id is not None:
                chat_ids.add(self.fwd_header.from_chat_id)
            if self.fwd_header.from_channel_id is not None:
                channel_ids.add(self.fwd_header.from_channel_id)
            if self.fwd_header.saved_peer_id is not None:
                self._fill_related_peer(self.fwd_header.saved_peer, user_ids, chat_ids, channel_ids)
            if self.fwd_header.saved_from_id is not None:
                user_ids.add(self.fwd_header.saved_from_id)

        if self.via_bot_id is not None:
            user_ids.add(self.via_bot_id)

    @classmethod
    async def _create_related_from_ids(
            cls, messages: Iterable[Message],
            user_ids: Iterable[int], chat_ids: Iterable[int], channel_ids: Iterable[int],
    ) -> None:
        related_users = []
        related_chats = []
        related_channels = []

        if user_ids:
            related_users = await models.User.filter(id__in=user_ids)
        if chat_ids:
            related_chats = await models.Chat.filter(id__in=chat_ids)
        if channel_ids:
            related_channels = await models.Channel.filter(id__in=channel_ids)

        await cls._create_related(messages, related_users, related_chats, related_channels)

    @staticmethod
    async def _create_related(
            messages: Iterable[Message],
            users: Iterable[models.User], chats: Iterable[models.Chat], channels: Iterable[models.Channel],
    ) -> None:
        related_to_create = [
            *(
                models.MessageRelated(message=message, user=rel)
                for message in messages
                for rel in users
            ),
            *(
                models.MessageRelated(message=message, chat=rel)
                for message in messages
                for rel in chats
            ),
            *(
                models.MessageRelated(message=message, channel=rel)
                for message in messages
                for rel in channels
            ),
        ]

        if related_to_create:
            await models.MessageRelated.bulk_create(related_to_create)

    # TODO: this has terrible performance for some reason (e.g. 70+ seconds for GetDialogs call)
    """
    def query_users_chats(
            self, users: Q | None = None, chats: Q | None = None, channels: Q | None = None,
    ) -> tuple[Q | None, Q | None, Q | None]:
        if users is not None and self.author_id is not None and not self.channel_post:
            users |= Q(id=self.author_id)
        if (users is not None or chats is not None or channels is not None) and self.peer_id is not None:
            users, chats, channels = models.Peer.query_users_chats_cls(self.peer_id, users, chats, channels)
        if users is not None:
            users |= Q(messagerelateds__message__id=self.id)
        if chats is not None:
            chats |= Q(messagerelateds__message__id=self.id)
        if channels is not None:
            channels |= Q(messagerelateds__message__id=self.id)

        return users, chats, channels
    """

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

        if self.via_bot_id is not None:
            users |= Q(id=self.via_bot_id)

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

    async def get_for_user(self, for_user: models.User) -> Message | None:
        if self.peer.type is PeerType.CHANNEL:
            return self

        if self.peer.type is PeerType.SELF:
            if for_user.id == self.peer.owner_id:
                return self
            return None

        if self.peer.type is PeerType.USER:
            return await Message.get_or_none(
                peer__owner=for_user, peer__user=self.peer.owner_id, internal_id=self.internal_id,
            ).select_related("peer", "author", "media")

        if self.peer.type is PeerType.CHAT:
            peer_for_user = await self.peer.get_for_user(for_user)
            return await Message.get_or_none(
                peer=peer_for_user, internal_id=self.internal_id,
            ).select_related("peer", "author", "media")

        raise Unreachable
