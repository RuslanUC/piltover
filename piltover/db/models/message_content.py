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
from piltover.db.enums import MessageType, PeerType, PrivacyRuleKeyType
from piltover.db.models.utils import Missing, MISSING, NullableFK, NullableFKSetNull
from piltover.exceptions import Unreachable
from piltover.tl import objects, TLObject
from piltover.tl.base import MessageActionInst, ReplyMarkupInst, ReplyMarkup, MessageMedia as MessageMediaBase, \
    MessageEntity as MessageEntityBase
from piltover.tl.base.internal import MessageToFormatContent as MessageToFormatContentBase
from piltover.tl.to_format import MessageServiceToFormat
from piltover.tl.to_format.message import MessageToFormat
from piltover.tl.types import PeerUser, MessageActionChatAddUser, \
    MessageActionChatDeleteUser, MessageReactions, ReactionCount, ReactionEmoji, MessageActionEmpty, \
    MessageEntityMentionName, MessageReplies, ReactionCustomEmoji
from piltover.tl.types.internal import MessageToFormatContent, MessageToFormatServiceContent

MessageIdRef = Annotated[int, "Ref id"]
MessageIdContent = Annotated[int, "Content id"]


class MessageContent(Model):
    id: int = fields.BigIntField(pk=True)
    message: str | None = fields.TextField(null=True, default=None)
    date: datetime = fields.DatetimeField(auto_now_add=True)
    edit_date: datetime = fields.DatetimeField(null=True, default=None)
    type: MessageType = fields.IntEnumField(MessageType, default=MessageType.REGULAR, description="")
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
    fwd_header: models.MessageFwdHeader | None = NullableFK("models.MessageFwdHeader")
    post_info: models.ChannelPostInfo | None = NullableFK("models.ChannelPostInfo")
    via_bot: models.User | None = NullableFKSetNull("models.User", related_name="msg_via_bot")
    discussion: models.MessageContent | None = NullableFKSetNull("models.MessageContent", related_name="msg_discussion_message")
    comments_info: models.MessageComments | None = NullableFK("models.MessageComments")
    is_discussion: bool = fields.BooleanField(default=False)
    version: int = fields.IntField(default=0)
    reactions_version: int = fields.IntField(default=0)

    peer_id: int
    author_id: int | None
    media_id: int | None
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

    def is_service(self) -> bool:
        return self.type not in (MessageType.REGULAR, MessageType.SCHEDULED)

    def to_tl_service(self, ref: models.MessageRef) -> MessageServiceToFormat:
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
            reply_to=ref.make_reply_to_header(),
            from_id=PeerUser(user_id=self.author_id) if not self.channel_post else None,
            ttl_period=self.ttl_period_days * self.TTL_MULT if self.ttl_period_days else None,
        )

    def to_tl_service_content(self) -> MessageToFormatServiceContent:
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
        return MessageToFormatServiceContent(
            date=int(self.date.timestamp()),
            action=action,
            from_id=PeerUser(user_id=self.author_id) if not self.channel_post else None,
            ttl_period=self.ttl_period_days * self.TTL_MULT if self.ttl_period_days else None,
        )

    def _to_tl_content(
            self, media: MessageMediaBase, entities: list[MessageEntityBase] | None,
            reactions: MessageReactions | None, replies: MessageReplies | None,
    ) -> MessageToFormatContent:
        ttl_period = None
        if self.ttl_period_days is not None and self.type is not MessageType.SCHEDULED:
            ttl_period = self.ttl_period_days * self.TTL_MULT

        # TODO: saved_peer_id
        # TODO: invert_media
        return MessageToFormatContent(
            message=self.message or "",
            date=int((self.date if self.scheduled_date is None else self.scheduled_date).timestamp()),
            media=media,
            edit_date=int(self.edit_date.timestamp()) if self.edit_date is not None else None,
            from_id=PeerUser(user_id=self.author_id) if not self.channel_post else None,
            entities=entities,
            grouped_id=self.media_group_id,
            post=self.channel_post,
            views=self.post_info.views if self.post_info_id is not None else None,
            forwards=self.post_info.forwards if self.post_info_id is not None else None,
            post_author=self.post_author if self.channel_post else None,
            ttl_period=ttl_period,
            reply_markup=self.make_reply_markup(),
            noforwards=self.no_forwards,
            via_bot_id=self.via_bot_id,
            replies=replies,
            edit_hide=self.edit_hide,
            min_reactions=reactions if reactions is not None and reactions.min else None,
            fwd_from=self.fwd_header.to_tl() if self.fwd_header_id is not None else None,
        )

    async def to_tl_content(
            self, to_format: MessageToFormat, with_reactions: bool, reactions: MessageReactions | None,
    ) -> MessageToFormatContentBase:
        # This function call is probably much cheaper than cache lookup, so doing this before Cache.obj.get(...)
        if self.is_service():
            return self.to_tl_service_content()

        cache_key = self.cache_key()
        if (cached := await Cache.obj.get(cache_key)) is not None:
            to_format.content = cached
            if with_reactions and self.type is MessageType.REGULAR:
                reactions_before = to_format.content.min_reactions
                to_format.reactions = reactions
                if reactions_before != to_format.content.min_reactions:
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

        replies = None
        if self.is_discussion:
            replies = MessageReplies(
                replies=await models.MessageRef.filter(reply_to__content=self).count(),
                # TODO: probably handle pts
                replies_pts=0,
            )
        elif self.discussion_id is not None and self.comments_info_id is not None:
            replies = MessageReplies(
                replies=await models.MessageRef.filter(reply_to__content_id=self.discussion_id).count(),
                replies_pts=self.comments_info.discussion_pts,
                comments=True,
                channel_id=models.Channel.make_id_from(self.comments_info.discussion_channel_id),
            )

        message = self._to_tl_content(
            media=media,
            entities=entities,
            reactions=reactions,
            replies=replies,
        )

        await Cache.obj.set(cache_key, message)
        return message

    @classmethod
    async def to_tl_content_bulk(
            cls, messages: list[models.MessageContent],
            to_formats: list[MessageToFormat], with_reactions: bool, reactionss: list[MessageReactions | None],
    ) -> list[MessageToFormatContentBase]:
        cached = []
        cache_keys = [message.cache_key() for message in messages]
        if cache_keys:
            # Assuming multi_get returns objects in the same order as cache_keys
            cached = await Cache.obj.multi_get(cache_keys)

        replies: dict[MessageIdContent, MessageReplies] = {}
        replies_count_to_fetch: dict[MessageIdContent, list[MessageIdContent]] = defaultdict(list)
        for idx, message in enumerate(messages):
            if cached[idx] is not None or message.is_service():
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
                for reply_to_id, count in await models.MessageRef.filter(
                    reply_to__content_id__in=list(replies_count_to_fetch),
                ).group_by("reply_to__content_id").annotate(
                    count=Count("id"),
                ).values_list(
                    "reply_to__content_id", "count",
                )
            }
            for reply_to_id, ids in replies_count_to_fetch.items():
                count = counts.get(reply_to_id, 0)
                for message_id in ids:
                    replies[message_id].replies = count

        medias_ = [message.media for message in messages if message.media is not None]
        medias = {
            media.id: media_tl
            for media, media_tl in zip(medias_, await models.MessageMedia.to_tl_bulk(medias_))
        }

        to_cache = []

        result: list[MessageToFormatContent | MessageToFormatServiceContent] = []
        for message, reactions, to_format, cached_message in zip(messages, reactionss, to_formats, cached):
            if message.is_service():
                result.append(message.to_tl_service_content())
                continue

            if cached_message is not None:
                to_format.content = cached_message
                result.append(cached_message)
                need_recache = False

                if with_reactions:
                    reactions_before = to_format.content.min_reactions
                    to_format.reactions = reactions
                    need_recache = reactions_before != to_format.content.min_reactions

                if need_recache:
                    to_cache.append((message.cache_key(), result[-1]))

                continue

            entities = []
            for entity in (message.entities or []):
                tl_id = entity.pop("_")
                entities.append(objects[tl_id](**entity))
                entity["_"] = tl_id

            result.append(message._to_tl_content(
                media=medias[message.media_id] if message.media_id is not None else None,
                entities=entities,
                reactions=reactions,
                replies=replies.get(message.id, None),
            ))

            to_cache.append((message.cache_key(), result[-1]))

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
            drop_captions: bool = False, media_group_id: int | None = None, drop_author: bool = False,
            is_forward: bool = False, no_forwards: bool = False, is_discussion: bool = False,
    ) -> Self:
        if new_author is None and self.author is not None:
            new_author = self.author

        content = await models.MessageContent.create(
            message=self.message if self.media is None or not drop_captions else None,
            date=self.date if not is_forward else datetime.now(UTC),
            edit_date=self.edit_date if not is_forward else None,
            type=self.type,
            author=new_author,
            media=self.media,
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

        user_reaction = await models.MessageReaction.get_or_none(
            user_id=user_id, message=self
        ).values_list("reaction_id", "custom_emoji_id")
        if user_reaction:
            user_reaction_id, user_custom_emoji_id = user_reaction
            cache_user_id = user_id
        elif self.author_id == user_id:
            user_reaction_id = user_custom_emoji_id = None
            cache_user_id = user_id
        else:
            user_reaction_id = user_custom_emoji_id = None
            cache_user_id = None

        if (cached := await Cache.obj.get(self.cache_key_reactions(cache_user_id))) is not None:
            return cached

        reactions = await models.MessageReaction\
            .annotate(msg_count=Count("id"))\
            .filter(message=self)\
            .group_by("reaction__id", "custom_emoji_id")\
            .select_related("reaction")\
            .values_list("reaction__id", "custom_emoji_id", "reaction__reaction", "msg_count")

        # TODO: if `user.id == self.author_id`, always include unread reaction in recent_reactions

        results = []

        for reaction_id, custom_emoji_id, reaction_emoji, msg_count in reactions:
            if reaction_id is not None:
                reaction = ReactionEmoji(emoticon=reaction_emoji)
            elif custom_emoji_id is not None:
                reaction = ReactionCustomEmoji(document_id=custom_emoji_id)
            else:
                raise Unreachable

            results.append(ReactionCount(
                chosen_order=1 if reaction_id == user_reaction_id and custom_emoji_id == user_custom_emoji_id else None,
                reaction=reaction,
                count=msg_count,
            ))

        recent_reactions = None
        # TODO: also fetch it if can_see_list is True
        if self.author_id == user_id:
            # TODO: fetch last_reaction_id

            recent_reactions = []

            for recent in await models.MessageReaction.filter(
                message=self,
            ).order_by("-date").limit(5).select_related("reaction"):
                recent_reactions.append(recent.to_tl_peer_reaction(user_id, 0))

        result = MessageReactions(
            min=cache_user_id is None,
            # TODO: set to True if:
            #  peer is self/user/chat,
            #  or peer is channel and channel is a supergroup and message author is current `user`
            can_see_list=False,
            results=results,
            recent_reactions=recent_reactions,
        )

        await Cache.obj.set(self.cache_key_reactions(cache_user_id), result)

        return result

    def cache_key(self) -> str:
        return f"message-content:{self.id}:{self.version}"

    def cache_key_reactions(self, user_id: int | None) -> str:
        return f"message-reactions:{self.id}:{user_id or 0}:{self.reactions_version}"
