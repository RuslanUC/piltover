from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from enum import Enum, auto
from io import BytesIO
from os import environ
from typing import cast, Iterable, TypeVar

from loguru import logger
from pytz import UTC
from tortoise import fields, Model
from tortoise.expressions import Q
from tortoise.functions import Count

from piltover.cache import Cache
from piltover.db import models
from piltover.db.enums import MessageType, PeerType, PrivacyRuleKeyType, FileType
from piltover.exceptions import ErrorRpc, Unreachable
from piltover.tl import MessageReplyHeader, objects, TLObject
from piltover.tl.base import MessageActionInst, ReplyMarkupInst, ReplyMarkup, Message as TLMessageBase, \
    MessageMedia as MessageMediaBase, MessageEntity as MessageEntityBase
from piltover.tl.to_format import MessageServiceToFormat
from piltover.tl.types import Message as TLMessage, PeerUser, MessageActionChatAddUser, \
    MessageActionChatDeleteUser, MessageReactions, ReactionCount, ReactionEmoji, MessageActionEmpty, \
    MessageEntityMentionName, MessageReplies
from piltover.utils.snowflake import Snowflake


_T = TypeVar("_T")
BackwardO2OOrT = fields.BackwardOneToOneRelation[_T] | _T


class _SomethingMissing(Enum):
    MISSING = auto()


_SMTH_MISSING = _SomethingMissing.MISSING


async def append_channel_min_message_id_to_query_maybe(
        peer: models.Peer, query: Q, participant: models.ChatParticipant | None = None,
) -> Q:
    if isinstance(peer, models.Peer) and peer.type is PeerType.CHANNEL:
        if participant is None:
            participant = await peer.channel.get_participant(peer.owner)
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
    # TODO: use BigIntField for random_id
    random_id: str | None = fields.CharField(max_length=24, null=True, default=None)
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
    media_read: bool = fields.BooleanField(default=False)
    edit_hide: bool = fields.BooleanField(default=False)

    author: models.User = fields.ForeignKeyField("models.User", on_delete=fields.SET_NULL, null=True)
    peer: models.Peer = fields.ForeignKeyField("models.Peer")
    media: models.MessageMedia | None = fields.ForeignKeyField("models.MessageMedia", null=True, default=None)
    reply_to: models.Message | None = fields.ForeignKeyField("models.Message", null=True, default=None, on_delete=fields.SET_NULL, related_name="msg_reply_to")
    fwd_header: models.MessageFwdHeader | None = fields.ForeignKeyField("models.MessageFwdHeader", null=True, default=None)
    post_info: models.ChannelPostInfo | None = fields.ForeignKeyField("models.ChannelPostInfo", null=True, default=None)
    via_bot: models.User | None = fields.ForeignKeyField("models.User", on_delete=fields.SET_NULL, null=True, default=None, related_name="msg_via_bot")
    discussion: models.Message | None = fields.ForeignKeyField("models.Message", null=True, default=None, on_delete=fields.SET_NULL, related_name="msg_discussion_message")
    comments_info: models.MessageComments | None = fields.ForeignKeyField("models.MessageComments", null=True, default=None)
    top_message: models.Message | None = fields.ForeignKeyField("models.Message", null=True, default=None, on_delete=fields.SET_NULL, related_name="msg_top_message")
    is_discussion: bool = fields.BooleanField(default=False)

    peer_id: int
    author_id: int | None
    media_id: int | None
    reply_to_id: int | None
    fwd_header_id: int | None
    post_info_id: int | None
    via_bot_id: int | None
    discussion_id: int | None
    top_message_id: int | None
    comments_info_id: int | None

    taskiqscheduledmessages: BackwardO2OOrT[models.TaskIqScheduledMessage]

    TTL_MULT = 86400
    if (_ttl_mult := environ.get("DEBUG_MESSAGE_TTL_MULTIPLIER", "")).isdigit():
        TTL_MULT = int(_ttl_mult)

    PREFETCH_FIELDS_MIN = (
        "peer", "author", "media",
    )
    PREFETCH_FIELDS = (
        *PREFETCH_FIELDS_MIN, "media__file", "media__file__stickerset", "media__poll", "fwd_header",
        "fwd_header__saved_peer", "post_info", "via_bot", "comments_info",
    )
    _PREFETCH_ALL_TOP_FIELDS = (
        "peer", "author", "media", "fwd_header", "reply_to", "via_bot",
    )

    _cached_reply_markup: ReplyMarkup | None | _SomethingMissing = _SMTH_MISSING

    class Meta:
        unique_together = (
            ("peer", "random_id"),
        )

    def _cache_key(self, user: models.User) -> str:
        media_version = None if self.media_id is None else self.media.version
        return f"message:{user.id}:{self.id}:{self.version}-{media_version}"

    @classmethod
    async def get_(
            cls, id_: int, peer: models.Peer, types: tuple[MessageType, ...] = (MessageType.REGULAR,),
            prefetch_all: bool = False,
    ) -> models.Message | None:
        types_query = Q()
        for message_type in types:
            types_query |= Q(type=message_type)
        peer_query = Q(peer=peer)
        if peer.type is PeerType.CHANNEL:
            peer_query |= Q(peer__owner=None, peer__channel__id=peer.channel_id)

        query = peer_query & types_query & Q(id=id_)
        query = await append_channel_min_message_id_to_query_maybe(peer, query)

        return await Message.get_or_none(query).select_related(
            *(cls.PREFETCH_FIELDS if prefetch_all else cls.PREFETCH_FIELDS_MIN)
        )

    @classmethod
    async def get_many(cls, ids: list[int], peer: models.Peer, prefetch_all: bool = False) -> list[models.Message]:
        peer_query = Q(peer=peer)
        if peer.type is PeerType.CHANNEL:
            peer_query |= Q(peer__owner=None, peer__channel__id=peer.channel_id)

        query = peer_query & Q(id__in=ids, type=MessageType.REGULAR)
        query = await append_channel_min_message_id_to_query_maybe(peer, query)

        return await Message.filter(query).select_related(
            *(cls.PREFETCH_FIELDS if prefetch_all else cls.PREFETCH_FIELDS_MIN)
        )

    def _make_reply_to_header(self) -> MessageReplyHeader | None:
        if self.reply_to_id is None and self.top_message_id is None:
            return None

        return MessageReplyHeader(
            reply_to_msg_id=self.reply_to_id,
            reply_to_top_id=self.top_message_id,
        )

    def is_service(self) -> bool:
        return self.type not in (MessageType.REGULAR, MessageType.SCHEDULED)

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

    def _to_tl(
            self, out: bool, media: MessageMediaBase, entities: list[MessageEntityBase] | None,
            reactions: MessageReactions | None, mentioned: bool, media_unread: bool, replies: MessageReplies | None,
    ) -> TLMessage:
        ttl_period = None
        if self.ttl_period_days is not None and self.type is not MessageType.SCHEDULED:
            ttl_period = self.ttl_period_days * self.TTL_MULT

        return TLMessage(
            id=self.id,
            message=self.message or "",
            pinned=self.pinned,
            peer_id=self.peer.to_tl(),
            date=int((self.date if self.scheduled_date is None else self.scheduled_date).timestamp()),
            out=out,
            media=media,
            edit_date=int(self.edit_date.timestamp()) if self.edit_date is not None else None,
            reply_to=self._make_reply_to_header(),
            fwd_from=self.fwd_header.to_tl() if self.fwd_header_id is not None else None,
            from_id=PeerUser(user_id=self.author_id) if not self.channel_post else None,
            entities=entities,
            grouped_id=self.media_group_id,
            post=self.channel_post,
            views=self.post_info.views if self.post_info_id is not None else None,
            forwards=self.post_info.forwards if self.post_info_id is not None else None,
            post_author=self.post_author if self.channel_post else None,
            reactions=reactions,
            mentioned=mentioned,
            media_unread=media_unread,
            from_scheduled=self.from_scheduled or self.scheduled_date is not None,
            ttl_period=ttl_period,
            reply_markup=self.make_reply_markup(),
            noforwards=self.no_forwards,
            via_bot_id=self.via_bot_id,
            replies=replies,
            edit_hide=self.edit_hide,

            silent=False,
            legacy=False,
            restriction_reason=[],
        )

    async def to_tl(self, current_user: models.User, with_reactions: bool = False) -> TLMessageBase:
        # This function call is probably much cheaper than cache lookup, so doing this before Cache.obj.get(...)
        if self.is_service():
            return self._to_tl_service()

        reactions = None
        if with_reactions and self.type is MessageType.REGULAR:
            reactions = await self.to_tl_reactions(current_user)

        cache_key = self._cache_key(current_user)
        if (cached := await Cache.obj.get(cache_key)) is not None:
            if with_reactions and self.type is MessageType.REGULAR:
                cached.reactions = reactions
                await Cache.obj.set(cache_key, cached)
            return cached

        media = None
        if self.media_id is not None:
            media = await self.media.to_tl(current_user) if self.media is not None else None

        entities = []
        for entity in (self.entities or []):
            tl_id = entity.pop("_")
            entities.append(objects[tl_id](**entity))
            entity["_"] = tl_id

        mentioned = await models.MessageMention.filter(peer__owner=current_user, message=self).exists()

        media_unread = False
        if self.media \
                and self.media.file \
                and self.media.file.type in (FileType.DOCUMENT_VOICE, FileType.DOCUMENT_VIDEO_NOTE):
            media_unread = not self.media_read
        elif mentioned:
            if self.peer.type is PeerType.CHANNEL:
                readstate_peer = Q(peer__owner=current_user, peer__channel__id=self.peer.channel_id)
            else:
                readstate_peer = Q(peer=self.peer)
            last_id = cast(
                int | None,
                await models.ReadState.filter(readstate_peer).first().values_list("last_mention_id", flat=True)
            )
            media_unread = last_id is None or last_id < self.id

        replies = None
        if self.is_discussion:
            replies = MessageReplies(
                replies=await models.Message.filter(reply_to=self).count(),
                # TODO: probably handle pts
                replies_pts=0,
            )
        elif self.discussion_id is not None and self.comments_info_id is not None:
            replies = MessageReplies(
                replies=await models.Message.filter(reply_to__id=self.discussion_id).count(),
                replies_pts=self.comments_info.discussion_pts,
                comments=True,
                channel_id=models.Channel.make_id_from(self.comments_info.discussion_channel_id),
            )

        message = self._to_tl(
            out=current_user.id == self.author_id,
            media=media,
            entities=entities,
            reactions=reactions,
            mentioned=mentioned,
            media_unread=media_unread,
            replies=replies,
        )

        await Cache.obj.set(cache_key, message)
        return message

    @classmethod
    async def to_tl_bulk(
            cls, messages: list[Message], user: models.User, with_reactions: bool = False,
    ) -> list[TLMessageBase]:
        cached = {}
        cache_keys = [message._cache_key(user) for message in messages]
        if cache_keys:
            cached = {
                cached_msg.id: cached_msg
                for cached_msg in await Cache.obj.multi_get(cache_keys)
                if cached_msg is not None
            }

        message_ids = {message.id for message in messages if message.id not in cached and not message.is_service()}

        if message_ids:
            mentioned = set(await models.MessageMention.filter(
                peer__owner=user, message__id__in=message_ids,
            ).values_list("message__id", flat=True))
        else:
            mentioned = set()

        media_unreads = {}
        last_mention_peers_to_fetch = set()
        last_mention_messages_to_check = set()
        for message in messages:
            if message.is_service():
                continue
            if message.media \
                    and message.media.file \
                    and message.media.file.type in (FileType.DOCUMENT_VOICE, FileType.DOCUMENT_VIDEO_NOTE):
                media_unreads[message.id] = not message.media_read
            elif message.id in mentioned:
                last_mention_peers_to_fetch.add(message.peer)
                last_mention_messages_to_check.add(message.id)

        if last_mention_peers_to_fetch:
            last_mentions_q = Q()
            for peer in last_mention_peers_to_fetch:
                if peer.type is PeerType.CHANNEL:
                    last_mentions_q |= Q(peer__owner=user, peer__channel__id=peer.channel_id)
                else:
                    last_mentions_q |= Q(peer=peer)

            last_ids_result = await models.ReadState.filter(last_mentions_q).values_list(
                "peer__type", "peer__user__id", "peer__chat__id", "peer__channel__id", "last_mention_id"
            )
            last_ids = {}
            for peer_type, peer_user, peer_chat, peer_channel, last_id in last_ids_result:
                if peer_type in (PeerType.SELF, PeerType.USER):
                    last_ids[(peer_type, peer_user)] = last_id
                elif peer_type is PeerType.CHAT:
                    last_ids[(peer_type, peer_chat)] = last_id
                elif peer_type is PeerType.CHANNEL:
                    last_ids[(peer_type, peer_channel)] = last_id
                else:
                    raise Unreachable

            for message in messages:
                if message.id not in last_mention_messages_to_check:
                    continue

                if message.peer.type in (PeerType.SELF, PeerType.USER):
                    key = (message.peer.type, message.peer.user_id)
                elif message.peer.type is PeerType.CHAT:
                    key = (message.peer.type, message.peer.chat_id)
                elif message.peer.type is PeerType.CHANNEL:
                    key = (message.peer.type, message.peer.channel_id)
                else:
                    raise Unreachable

                if key not in last_ids or last_ids[key] < message.id:
                    media_unreads[message.id] = True

        replies = {}
        replies_count_to_fetch = defaultdict(list)
        for message in messages:
            if message.id in cached or message.is_service():
                continue
            if message.is_discussion:
                replies_count_to_fetch[message.id].append(message.id)
                replies[message.id] = MessageReplies(
                    replies=0,
                    # TODO: probably handle pts
                    replies_pts=0,
                )
            elif message.discussion_id is not None and message.comments_info_id is not None:
                replies_count_to_fetch[message.discussion_id].append(message.id)
                replies[message.id] = MessageReplies(
                    replies=0,
                    replies_pts=message.comments_info.discussion_pts,
                    comments=True,
                    channel_id=models.Channel.make_id_from(message.comments_info.discussion_channel_id),
                )

        if replies_count_to_fetch:
            counts = {
                reply_to_id: count
                for reply_to_id, count in await models.Message.filter(
                    reply_to__id__in=list(replies_count_to_fetch),
                ).group_by("reply__to__id").annotate(count=Count("id")).values_list("reply__to__id", "count")
            }
            for reply_to_id, ids in replies_count_to_fetch:
                count = counts.get(reply_to_id, 0)
                for message_id in ids:
                    replies[message_id].replies = count

        to_cache = []

        result = []
        for message in messages:
            if message.is_service():
                result.append(message._to_tl_service())
                continue

            msg_media_unread = media_unreads.get(message.id, False)

            reactions = None
            if with_reactions and message.type is MessageType.REGULAR:
                # TODO: precalculate reactions for all regular messages before loop
                reactions = await message.to_tl_reactions(user)
            
            if message.id in cached:
                result.append(cached[message.id])
                need_recache = False
                
                if result[-1].media_unread != msg_media_unread:
                    result[-1].media_unread = msg_media_unread
                    need_recache = True
                
                if with_reactions:
                    result[-1].reactions = reactions
                    need_recache = True
                
                if need_recache:
                    to_cache.append((message._cache_key(user), result[-1]))
                
                continue

            media = None
            if message.media_id is not None:
                # TODO: precalculate for all messages before loop somehow
                media = await message.media.to_tl(user) if message.media is not None else None

            entities = []
            for entity in (message.entities or []):
                tl_id = entity.pop("_")
                entities.append(objects[tl_id](**entity))
                entity["_"] = tl_id

            result.append(message._to_tl(
                out=user.id == message.author_id,
                media=media,
                entities=entities,
                reactions=reactions,
                mentioned=message.id in mentioned,
                media_unread=msg_media_unread,
                replies=replies.get(message.id, None),
            ))

            to_cache.append((message._cache_key(user), result[-1]))

        if to_cache:
            await Cache.obj.multi_set(to_cache)

        return result

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
            # TODO: probably create in bulk too?
            messages[to_peer] = await Message.create(
                from_scheduled=to_peer == self.peer,
                internal_id=self.internal_id,
                message=self.message,
                date=send_date,
                type=MessageType.REGULAR,
                author=self.author,
                peer=to_peer,
                media=self.media,
                # TODO: shouldn't reply_to be different for every peer ???
                reply_to=self.reply_to,
                fwd_header=self.fwd_header,
                entities=self.entities,
                media_group_id=self.media_group_id,
                channel_post=self.channel_post,
                post_author=self.post_author,
                post_info=self.post_info,
                ttl_period_days=self.ttl_period_days,
            )

        await models.Dialog.create_or_unhide_bulk(peers)

        related_users, related_chats, related_channels = await models.MessageRelated.get_for_message(self)
        await self._create_related(messages.values(), related_users, related_chats, related_channels)

        return messages

    async def clone_for_peer(
            self, peer: models.Peer, new_author: models.User | None = None, internal_id: int | None = None,
            random_id: int | None = None,
            fwd_header: models.MessageFwdHeader | None | _SomethingMissing = _SMTH_MISSING,
            reply_to_internal_id: int | None = None, drop_captions: bool = False, media_group_id: int | None = None,
            drop_author: bool = False, is_forward: bool = False, no_forwards: bool = False, pinned: bool | None = None,
            is_discussion: bool = False,
    ) -> models.Message:
        if new_author is None and self.author is not None:
            new_author = self.author

        reply_to = None
        if reply_to_internal_id:
            reply_to = await Message.get_or_none(peer=peer, internal_id=reply_to_internal_id)
        else:
            if self.reply_to_id is not None:
                reply_to = await Message.get_or_none(peer=peer, internal_id=self.reply_to.internal_id)

        if fwd_header is _SMTH_MISSING:
            # TODO: probably should be prefetched
            fwd_header = await self.fwd_header

        message = await Message.create(
            internal_id=internal_id or Snowflake.make_id(),
            message=self.message if self.media is None or not drop_captions else None,
            pinned=self.pinned if pinned is None else pinned,
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
            is_discussion=is_discussion,
        )

        related_user_ids = set()
        related_chat_ids = set()
        related_channel_ids = set()
        message._fill_related(related_user_ids, related_chat_ids, related_channel_ids)
        await self._create_related_from_ids((message,), related_user_ids, related_chat_ids, related_channel_ids)

        return message

    async def create_fwd_header(
            self, peer: models.Peer | None, discussion: bool = False,
    ) -> models.MessageFwdHeader:
        # TODO: pass prefetched privacy rules as an argument

        if self.fwd_header is not None and not discussion:
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

        is_self = peer is not None and peer.type is PeerType.SELF

        saved_peer = self.peer if is_self or discussion else None
        if saved_peer is not None and saved_peer.type is PeerType.USER:
            peer_ = self.peer
            if not await models.PrivacyRule.has_access_to(peer_.owner_id, peer_.user_id, PrivacyRuleKeyType.FORWARDS):
                saved_peer = None

        return await models.MessageFwdHeader.create(
            from_user=from_user,
            from_chat=from_chat,
            from_channel=from_channel,
            from_name=from_name,
            date=self.fwd_header.date if self.fwd_header else self.date,
            saved_out=not discussion,

            channel_post_id=channel_post_id,
            channel_post_author=channel_post_author,

            saved_peer=saved_peer,
            saved_id=self.id if is_self or discussion else None,
            saved_from=self.author if is_self else None,
            saved_name=self.author.first_name if is_self else None,
            saved_date=self.date if is_self else None,
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

        replies = {
            message.peer_id: message
            for message in await Message.filter(peer__id__in=[p.id for p in peers], internal_id=reply.internal_id)
        } if reply else {}

        internal_id = Snowflake.make_id()
        for to_peer in peers:
            messages[to_peer] = message = await Message.create(
                internal_id=internal_id,
                peer=to_peer,
                reply_to=replies.get(to_peer.id, None),
                author=author,
                random_id=str(random_id) if to_peer == peer and random_id is not None else None,
                **message_kwargs,
            )
            message._fill_related(related_user_ids, related_chat_ids, related_channel_ids)

        if unhide_dialog:
            await models.Dialog.create_or_unhide_bulk(peers)

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
            ).select_related(*self.PREFETCH_FIELDS_MIN)

        if self.peer.type is PeerType.CHAT:
            peer_for_user = await self.peer.get_for_user(for_user)
            return await Message.get_or_none(
                peer=peer_for_user, internal_id=self.internal_id,
            ).select_related(*self.PREFETCH_FIELDS_MIN)

        raise Unreachable
