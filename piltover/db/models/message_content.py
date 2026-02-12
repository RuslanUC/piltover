from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from io import BytesIO
from os import environ
from typing import Iterable, Self, Annotated

from loguru import logger
from pytz import UTC
from tortoise import fields, Model
from tortoise.functions import Count

from piltover.cache import Cache
from piltover.db import models
from piltover.db.enums import MessageType, PeerType, PrivacyRuleKeyType, READABLE_FILE_TYPES
from piltover.db.models.utils import Missing, MISSING, NullableFK, NullableFKSetNull
from piltover.tl import MessageReplyHeader, objects, TLObject
from piltover.tl.base import MessageActionInst, ReplyMarkupInst, ReplyMarkup, Message as TLMessageBase, \
    MessageMedia as MessageMediaBase, MessageEntity as MessageEntityBase
from piltover.tl.to_format import MessageServiceToFormat
from piltover.tl.types import Message as TLMessage, PeerUser, MessageActionChatAddUser, \
    MessageActionChatDeleteUser, MessageReactions, ReactionCount, ReactionEmoji, MessageActionEmpty, \
    MessageEntityMentionName, MessageReplies

MessageIdRef = Annotated[int, "Ref id"]
MessageIdContent = Annotated[int, "Content id"]


class MessageContent(Model):
    id: int = fields.BigIntField(pk=True)
    message: str | None = fields.TextField(null=True, default=None)
    date: datetime = fields.DatetimeField(default=lambda: datetime.now(UTC))
    edit_date: datetime = fields.DatetimeField(null=True, default=None)
    type: MessageType = fields.IntEnumField(MessageType, default=MessageType.REGULAR)
    # TODO: use tl for entities
    entities: list[dict] | None = fields.JSONField(null=True, default=None)
    extra_info: bytes | None = fields.BinaryField(null=True, default=None)
    media_group_id: int = fields.BigIntField(null=True, default=None)
    channel_post: bool = fields.BooleanField(default=False)
    post_author: str | None = fields.CharField(max_length=128, null=True, default=None)
    scheduled_date: datetime | None = fields.DatetimeField(null=True, default=None)
    ttl_period_days: int | None = fields.SmallIntField(null=True, default=None)
    # TODO: create fields type for tl objects
    reply_markup: bytes | None = fields.BinaryField(null=True, default=None)
    no_forwards: bool = fields.BooleanField(default=False)
    edit_hide: bool = fields.BooleanField(default=False)

    author: models.User = fields.ForeignKeyField("models.User", on_delete=fields.SET_NULL, null=True)
    media: models.MessageMedia | None = NullableFK("models.MessageMedia")
    # TODO: move to MessageRef model because resulting id is peer-dependent?
    reply_to: models.MessageContent | None = NullableFKSetNull("models.MessageContent", related_name="msg_reply_to")
    fwd_header: models.MessageFwdHeader | None = NullableFK("models.MessageFwdHeader")
    post_info: models.ChannelPostInfo | None = NullableFK("models.ChannelPostInfo")
    via_bot: models.User | None = NullableFKSetNull("models.User", related_name="msg_via_bot")
    discussion: models.MessageContent | None = NullableFKSetNull("models.MessageContent", related_name="msg_discussion_message")
    comments_info: models.MessageComments | None = NullableFK("models.MessageComments")
    # TODO: move to MessageRef model?
    top_message: models.MessageContent | None = NullableFKSetNull("models.MessageContent", related_name="msg_top_message")
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

    TTL_MULT = 86400
    if (_ttl_mult := environ.get("DEBUG_MESSAGE_TTL_MULTIPLIER", "")).isdigit():
        TTL_MULT = int(_ttl_mult)

    _cached_reply_markup: ReplyMarkup | None | Missing = MISSING

    async def _make_reply_to_header(self, peer: models.Peer) -> MessageReplyHeader | None:
        if self.reply_to_id is None and self.top_message_id is None:
            return None

        content_ids: set[int | None] = {self.reply_to_id, self.top_message_id}
        content_ids.discard(None)

        ids = await models.MessageRef.filter(content__id__in=content_ids, peer=peer).values_list("id", "content__id")
        if not ids:
            return None

        header = MessageReplyHeader()
        for ref_id, content_id in ids:
            if content_id == self.reply_to_id:
                header.reply_to_msg_id = ref_id
            elif content_id == self.top_message_id:
                header.reply_to_top_id = ref_id

        return header

    def is_service(self) -> bool:
        return self.type not in (MessageType.REGULAR, MessageType.SCHEDULED)

    async def to_tl_service(self, ref: models.MessageRef) -> MessageServiceToFormat:
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
            id=ref.id,
            peer_id=ref.peer.to_tl(),
            date=int(self.date.timestamp()),
            action=action,
            author_id=self.author_id,
            reply_to=await self._make_reply_to_header(ref.peer),
            from_id=PeerUser(user_id=self.author_id) if not self.channel_post else None,
            ttl_period=self.ttl_period_days * self.TTL_MULT if self.ttl_period_days else None,
        )

    def _to_tl(
            self, ref: models.MessageRef, out: bool, media: MessageMediaBase,
            entities: list[MessageEntityBase] | None, reactions: MessageReactions | None, mentioned: bool,
            media_unread: bool, replies: MessageReplies | None, reply_to: MessageReplyHeader | None,
    ) -> TLMessage:
        ttl_period = None
        if self.ttl_period_days is not None and self.type is not MessageType.SCHEDULED:
            ttl_period = self.ttl_period_days * self.TTL_MULT

        return TLMessage(
            id=ref.id,
            message=self.message or "",
            pinned=ref.pinned,
            peer_id=ref.peer.to_tl(),
            date=int((self.date if self.scheduled_date is None else self.scheduled_date).timestamp()),
            out=out,
            media=media,
            edit_date=int(self.edit_date.timestamp()) if self.edit_date is not None else None,
            reply_to=reply_to,
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
            from_scheduled=ref.from_scheduled or self.scheduled_date,
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

    async def to_tl(
            self, ref: models.MessageRef, current_user: models.User, with_reactions: bool = False,
    ) -> TLMessageBase:
        # This function call is probably much cheaper than cache lookup, so doing this before Cache.obj.get(...)
        if self.is_service():
            return await self.to_tl_service(ref)

        reactions = None
        if with_reactions and self.type is MessageType.REGULAR:
            reactions = await self.to_tl_reactions(current_user)

        cache_key = ref.cache_key(current_user.id)
        if (cached := await Cache.obj.get(cache_key)) is not None:
            if with_reactions and self.type is MessageType.REGULAR:
                cached.reactions = reactions
                await Cache.obj.set(cache_key, cached)
            return cached

        media = None
        if self.media_id is not None:
            media = await self.media.to_tl() if self.media is not None else None

        entities = []
        for entity in (self.entities or []):
            tl_id = entity.pop("_")
            entities.append(objects[tl_id](**entity))
            entity["_"] = tl_id

        mention_read = await models.MessageMention.filter(
            user=current_user, message=self
        ).first().values_list("read", flat=True)
        mentioned = mention_read is not None
        if not mentioned:
            mention_read = True

        media_unread = False
        if self.media \
                and self.media.file \
                and self.media.file.type in READABLE_FILE_TYPES:
            media_unread = not await models.MessageMediaRead.filter(user__id=current_user.id, message=ref).exists()

        replies = None
        if self.is_discussion:
            replies = MessageReplies(
                replies=await models.MessageContent.filter(reply_to=self).count(),
                # TODO: probably handle pts
                replies_pts=0,
                # max_id=cast(
                #     int | None,
                #     await models.MessageRef.filter(
                #         content__reply_to=self,
                #     ).order_by("-id").first().values_list("id", flat=True),
                # ),
            )
        elif self.discussion_id is not None and self.comments_info_id is not None:
            replies = MessageReplies(
                replies=await models.MessageContent.filter(reply_to__id=self.discussion_id).count(),
                replies_pts=self.comments_info.discussion_pts,
                # max_id=cast(
                #     int | None,
                #     await models.MessageRef.filter(
                #         content__reply_to__id=self.discussion_id,
                #     ).order_by("-id").first().values_list("id", flat=True),
                # ),
                comments=True,
                channel_id=models.Channel.make_id_from(self.comments_info.discussion_channel_id),
            )

        message = self._to_tl(
            ref=ref,
            out=current_user.id == self.author_id,
            media=media,
            entities=entities,
            reactions=reactions,
            mentioned=mentioned,
            media_unread=media_unread if media_unread else not mention_read,
            replies=replies,
            reply_to=await self._make_reply_to_header(ref.peer),
        )

        await Cache.obj.set(cache_key, message)
        return message

    @classmethod
    async def to_tl_bulk(
            cls, messages: list[models.MessageContent], refs: list[models.MessageRef], user_id: int,
            with_reactions: bool = False,
    ) -> list[TLMessageBase]:
        cached = {}
        cache_keys = [ref.cache_key(user_id) for message, ref in zip(messages, refs)]
        if cache_keys:
            cached = {
                cached_msg.id: cached_msg
                for cached_msg in await Cache.obj.multi_get(cache_keys)
                if cached_msg is not None
            }

        # TODO: move all mentioned/media_read -related stuff to MessageRef?

        message_content_ids = {
            message.id
            for message in messages
            if message.id not in cached and not message.is_service()
        }

        mentioned: dict[MessageIdContent, bool] = {}

        if message_content_ids:
            mentions_info = await models.MessageMention.filter(
                user__id=user_id, message__id__in=message_content_ids,
            ).values_list("message__id", "read")
            for message_id, read in mentions_info:
                mentioned[message_id] = read

        valid_media_ref_ids = [
            ref.id
            for ref in refs
            if (
                    ref.content.media is not None
                    and ref.content.media.file is not None
                    and ref.content.media.file.type in READABLE_FILE_TYPES
            )
        ]

        if valid_media_ref_ids:
            media_read = set(await models.MessageMediaRead.filter(
                user__id=user_id, message__id__in=valid_media_ref_ids,
            ).values_list("message__id", flat=True))
        else:
            media_read = set()

        replies: dict[MessageIdContent, MessageReplies] = {}
        replies_count_to_fetch: dict[MessageIdContent, list[MessageIdContent]] = defaultdict(list)
        for message in messages:
            if (message.id in cached) or message.is_service():
                continue
            if message.is_discussion:
                replies_count_to_fetch[message.id].append(message.id)
                replies[message.id] = MessageReplies(
                    replies=0,
                    # max_id=0,
                    # TODO: probably handle pts
                    replies_pts=0,
                )
            elif message.discussion_id is not None and message.comments_info_id is not None:
                replies_count_to_fetch[message.discussion_id].append(message.id)
                replies[message.id] = MessageReplies(
                    replies=0,
                    # max_id=0,
                    replies_pts=message.comments_info.discussion_pts,
                    comments=True,
                    channel_id=models.Channel.make_id_from(message.comments_info.discussion_channel_id),
                )

        if replies_count_to_fetch:
            counts = {
                reply_to_id: count
                for reply_to_id, count in await cls.filter(
                    reply_to__id__in=list(replies_count_to_fetch),
                ).group_by("reply_to__id").annotate(
                    count=Count("id"), #max_id=Max("messagerefs__id"),
                ).values_list(
                    "reply_to__id", "count", #"max_id"
                )
            }
            for reply_to_id, ids in replies_count_to_fetch.items():
                count = counts.get(reply_to_id, 0)
                for message_id in ids:
                    replies[message_id].replies = count
                    # replies[message_id].max_id = max_id

        medias_ = [message.media for message in messages if message.media is not None]
        medias = {
            media.id: media_tl
            for media, media_tl in zip(medias_, await models.MessageMedia.to_tl_bulk(medias_))
        }

        to_cache = []

        result = []
        for message, ref in zip(messages, refs):
            if message.is_service():
                # TODO: probably cache it?
                result.append(await message.to_tl_service(ref))
                continue

            msg_media_unread = ref.id not in media_read and not mentioned.get(message.id, True)

            reactions = None
            if with_reactions and message.type is MessageType.REGULAR:
                # TODO: precalculate reactions for all regular messages before loop
                reactions = await message.to_tl_reactions(user_id)
            
            if message.id in cached:
                result.append(cached[ref.id])
                need_recache = False
                
                if result[-1].media_unread != msg_media_unread:
                    result[-1].media_unread = msg_media_unread
                    need_recache = True
                
                if with_reactions:
                    result[-1].reactions = reactions
                    need_recache = True
                
                if need_recache:
                    to_cache.append((ref.cache_key(user_id), result[-1]))
                
                continue

            entities = []
            for entity in (message.entities or []):
                tl_id = entity.pop("_")
                entities.append(objects[tl_id](**entity))
                entity["_"] = tl_id

            result.append(message._to_tl(
                ref=ref,
                out=user_id == message.author_id,
                media=medias[message.media_id] if message.media_id is not None else None,
                entities=entities,
                reactions=reactions,
                mentioned=message.id in mentioned,
                media_unread=msg_media_unread,
                replies=replies.get(message.id, None),
                # TODO: move out of the loop
                reply_to=await message._make_reply_to_header(ref.peer),
            ))

            to_cache.append((ref.cache_key(user_id), result[-1]))

        if to_cache:
            await Cache.obj.multi_set(to_cache)

        return result

    def make_reply_markup(self) -> ReplyMarkup | None:
        if self._cached_reply_markup is MISSING:
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
        self._cached_reply_markup = MISSING

    async def clone_scheduled(self) -> Self:
        content = await models.MessageContent.create(
            message=self.message,
            date=datetime.now(UTC),
            type=MessageType.REGULAR,
            author=self.author,
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
        await self._create_related(content, related_users, related_chats, related_channels)

        return content

    async def clone_forward(
            self, related_peer: models.Peer, new_author: models.User | None = None,
            fwd_header: models.MessageFwdHeader | None | Missing = MISSING,
            reply_to_content_id: int | None = None, drop_captions: bool = False, media_group_id: int | None = None,
            drop_author: bool = False, is_forward: bool = False, no_forwards: bool = False,
            is_discussion: bool = False,
    ) -> Self:
        if new_author is None and self.author is not None:
            new_author = self.author

        reply_to = None
        if reply_to_content_id:
            reply_to = await models.MessageContent.get_or_none(id=reply_to_content_id)

        if fwd_header is MISSING:
            # TODO: probably should be prefetched
            fwd_header = await self.fwd_header

        content = await models.MessageContent.create(
            message=self.message if self.media is None or not drop_captions else None,
            date=self.date if not is_forward else datetime.now(UTC),
            edit_date=self.edit_date if not is_forward else None,
            type=self.type,
            author=new_author,
            media=self.media,
            reply_to=reply_to,
            fwd_header=fwd_header,
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
        content._fill_related(related_user_ids, related_chat_ids, related_channel_ids, related_peer)
        await self._create_related_from_ids(content, related_user_ids, related_chat_ids, related_channel_ids)

        return content

    async def create_fwd_header(
            self, ref: models.MessageRef, to_self: bool, discussion: bool = False,
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
                from_channel = ref.peer.channel
                from_name = from_channel.name
                channel_post_id = ref.id
                channel_post_author = self.post_author
            else:
                # TODO: handle anonymous admins in chats and channels
                if await models.PrivacyRule.has_access_to(ref.peer.owner_id, self.author, PrivacyRuleKeyType.FORWARDS):
                    from_user = self.author
                from_name = self.author.first_name

        saved_peer = ref.peer if to_self or discussion else None
        if saved_peer is not None and saved_peer.type is PeerType.USER:
            peer_ = ref.peer
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
            saved_id=ref.id if to_self or discussion else None,
            saved_from=self.author if to_self else None,
            saved_name=self.author.first_name if to_self else None,
            saved_date=self.date if to_self else None,
        )

    @classmethod
    async def create_for_peer(cls, related_peer: models.Peer, **message_kwargs) -> Self:
        related_user_ids: set[int] = set()
        related_chat_ids: set[int] = set()
        related_channel_ids: set[int] = set()

        content = await MessageContent.create(**message_kwargs)

        content._fill_related(related_user_ids, related_chat_ids, related_channel_ids, related_peer)
        await cls._create_related_from_ids(content, related_user_ids, related_chat_ids, related_channel_ids)

        return content

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
            related_peer: models.Peer | None = None,
    ) -> None:
        if related_peer is not None:
            self._fill_related_peer(related_peer, user_ids, chat_ids, channel_ids)

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
            cls, message: MessageContent,
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

        await cls._create_related(message, related_users, related_chats, related_channels)

    @staticmethod
    async def _create_related(
            message: MessageContent,
            users: Iterable[models.User], chats: Iterable[models.Chat], channels: Iterable[models.Channel],
    ) -> None:
        related_to_create = [
            *(
                models.MessageRelated(message=message, user=rel)
                for rel in users
            ),
            *(
                models.MessageRelated(message=message, chat=rel)
                for rel in chats
            ),
            *(
                models.MessageRelated(message=message, channel=rel)
                for rel in channels
            ),
        ]

        if related_to_create:
            await models.MessageRelated.bulk_create(related_to_create)

    async def to_tl_reactions(self, user: models.User | int) -> MessageReactions:
        user_id = user.id if isinstance(user, models.User) else user

        # TODO: send min MessageReactions if current user didn't send reaction to message
        user_reaction = await models.MessageReaction.get_or_none(user__id=user_id, message=self)
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
