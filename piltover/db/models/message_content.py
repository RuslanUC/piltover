from __future__ import annotations

import asyncio
from datetime import datetime, UTC
from io import BytesIO
from os import environ
from typing import Iterable, Self, Annotated, Sequence
from uuid import uuid4, UUID

from loguru import logger
from tortoise import fields, Model
from tortoise.transactions import in_transaction

from piltover.cache import Cache
from piltover.db import models
from piltover.db.enums import MessageType, PeerType, PrivacyRuleKeyType
from piltover.db.models.utils import Missing, MISSING, NullableFK, NullableFKSetNull
from piltover.tl import objects, TLObject
from piltover.tl.base import MessageActionInst, ReplyMarkupInst, ReplyMarkup, MessageMedia as MessageMediaBase, \
    MessageEntity as MessageEntityBase
from piltover.tl.base.internal import MessageToFormatContent as MessageToFormatContentBase
from piltover.tl.to_format import MessageServiceToFormat
from piltover.tl.types import PeerUser, MessageActionChatAddUser, \
    MessageActionChatDeleteUser, MessageActionEmpty, \
    MessageEntityMentionName, PeerChannel
from piltover.tl.types.internal import MessageToFormatContent, MessageToFormatServiceContent

MessageIdRef = Annotated[int, "Ref id"]
MessageIdContent = Annotated[int, "Content id"]


class MessageContent(Model):
    id: int = fields.BigIntField(primary_key=True)
    message: str | None = fields.CharField(max_length=8192, null=True, default=None, db_index=True)
    date: datetime = fields.DatetimeField(auto_now_add=True)
    edit_date: datetime = fields.DatetimeField(null=True, default=None)
    type: MessageType = fields.IntEnumField(MessageType, default=MessageType.REGULAR, description="")
    # TODO: use tl for entities
    entities: list[dict] | None = fields.JSONField(null=True, default=None)
    extra_info: bytes | None = fields.BinaryField(null=True, default=None)
    media_group_id: int = fields.BigIntField(null=True, default=None)
    channel_post: bool = fields.BooleanField(default=False)
    anonymous: bool = fields.BooleanField(default=False)
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
    version: int = fields.IntField(default=0)
    reactions_version: int = fields.IntField(default=0)
    replies_version: int = fields.IntField(default=0)
    send_as_channel: models.Channel | None = NullableFK("models.Channel")
    author_reactions_unread: bool = fields.BooleanField(default=False)
    internal_random_id: UUID | None = fields.UUIDField(null=True, default=None, unique=True)

    peer_id: int
    author_id: int | None
    media_id: int | None
    fwd_header_id: int | None
    post_info_id: int | None
    via_bot_id: int | None
    discussion_id: int | None
    comments_info_id: int | None
    send_as_channel_id: int | None

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
            from_id=PeerUser(user_id=self.author_id) if not (self.channel_post or self.anonymous) else None,
            ttl_period=self.ttl_period_days * self.TTL_MULT if self.ttl_period_days else None,
        )

    def _make_from_id(self) -> PeerUser | PeerChannel | None:
        if self.send_as_channel_id is not None:
            return PeerChannel(channel_id=models.Channel.make_id_from(self.send_as_channel_id))
        if not (self.channel_post or self.anonymous):
            return PeerUser(user_id=self.author_id)
        return None

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
            from_id=self._make_from_id(),
            ttl_period=self.ttl_period_days * self.TTL_MULT if self.ttl_period_days else None,
        )

    def _to_tl_content(
            self, media: MessageMediaBase, entities: list[MessageEntityBase] | None,
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
            from_id=self._make_from_id(),
            entities=entities,
            grouped_id=self.media_group_id,
            post=self.channel_post,
            views=self.post_info.views if self.post_info_id is not None else None,
            forwards=self.post_info.forwards if self.post_info_id is not None else None,
            post_author=self.post_author if self.channel_post or self.anonymous else None,
            ttl_period=ttl_period,
            reply_markup=self.make_reply_markup(),
            noforwards=self.no_forwards,
            via_bot_id=self.via_bot_id,
            edit_hide=self.edit_hide,
            fwd_from=self.fwd_header.to_tl() if self.fwd_header_id is not None else None,
        )

    async def to_tl_content(self) -> MessageToFormatContentBase:
        # This function call is probably much cheaper than cache lookup, so doing this before Cache.obj.get(...)
        if self.is_service():
            return self.to_tl_service_content()

        cache_key = self.cache_key()
        if (cached := await Cache.obj.get(cache_key)) is not None:
            return cached

        media = None
        if self.media_id is not None:
            media = await self.media.to_tl() if self.media is not None else None

        entities = []
        for entity in (self.entities or []):
            tl_id = entity.pop("_")
            entities.append(objects[tl_id](**entity))
            entity["_"] = tl_id

        message = self._to_tl_content(media=media, entities=entities)

        await Cache.obj.set(cache_key, message)
        return message

    @classmethod
    async def to_tl_content_bulk(cls, messages: list[models.MessageContent]) -> list[MessageToFormatContentBase]:
        if not messages:
            return []

        cache_keys = [message.cache_key() for message in messages]
        cached = await Cache.obj.multi_get(cache_keys)

        medias_ = [message.media for message in messages if message.media is not None]
        medias = {
            media.id: media_tl
            for media, media_tl in zip(medias_, await models.MessageMedia.to_tl_bulk(medias_))
        }

        to_cache = []

        result: list[MessageToFormatContent | MessageToFormatServiceContent] = []
        for message, cached_message in zip(messages, cached):
            if message.is_service():
                result.append(message.to_tl_service_content())
                continue

            if cached_message is not None:
                result.append(cached_message)
                continue

            entities = []
            for entity in (message.entities or []):
                tl_id = entity.pop("_")
                entities.append(objects[tl_id](**entity))
                entity["_"] = tl_id

            result.append(message._to_tl_content(
                media=medias[message.media_id] if message.media_id is not None else None,
                entities=entities,
            ))

            to_cache.append((message.cache_key(), result[-1]))

        if to_cache:
            await Cache.obj.multi_set(to_cache)

        return result

    async def to_tl_content_cached(self) -> MessageToFormatContent | None:
        return await Cache.obj.get(self.cache_key())

    @classmethod
    async def to_tl_ref_bulk_cached(cls, refs: list[models.MessageContent]) -> list[MessageToFormatContent | None]:
        cache_keys = [ref.cache_key() for ref in refs]
        if not cache_keys:
            return []
        return await Cache.obj.multi_get(cache_keys)

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
            anonymous=self.anonymous,
            post_author=self.post_author,
            post_info=self.post_info,
            ttl_period_days=self.ttl_period_days,
            send_as_channel_id=self.send_as_channel_id,
        )

        related_user_ids, related_chat_ids, related_channel_ids = await models.MessageRelated.get_for_message(self)
        await self._create_related(content, related_user_ids, related_chat_ids, related_channel_ids)

        return content

    async def clone_forward(
            self, related_peer: models.Peer, new_author: models.User | None = None,
            # TODO: make required
            fwd_header: models.MessageFwdHeader | None = None,
            drop_captions: bool = False, media_group_id: int | None = None, drop_author: bool = False,
            is_forward: bool = False, no_forwards: bool = False,
            new_channel_author_id: int | None = None, channel_post: bool | None = None,
            post_info: models.ChannelPostInfo | None = None, post_author: str | None = None,
            anonymous: bool | None = None,
    ) -> Self:
        if new_author is None and self.author is not None:
            new_author = self.author
        if new_channel_author_id is None and self.send_as_channel_id is not None:
            new_channel_author_id = self.send_as_channel_id

        if anonymous is None:
            anonymous = self.anonymous if not drop_author else None
        if channel_post is None:
            channel_post = self.channel_post if not drop_author else None
        if post_info is None:
            post_info = self.post_info if not drop_author else None
        if post_author is None:
            post_author = self.post_author if not drop_author else None

        content = await models.MessageContent.create(
            message=self.message if self.media is None or not drop_captions else None,
            entities=self.entities if self.media is None or not drop_captions else None,
            date=self.date if not is_forward else datetime.now(UTC),
            edit_date=self.edit_date if not is_forward else None,
            type=self.type,
            author=new_author,
            media=self.media,
            fwd_header=fwd_header,
            media_group_id=media_group_id,
            channel_post=channel_post,
            post_author=post_author,
            post_info=post_info,
            anonymous=anonymous,
            no_forwards=no_forwards,
            via_bot=self.via_bot,
            send_as_channel_id=new_channel_author_id,
        )

        related_user_ids = set()
        related_chat_ids = set()
        related_channel_ids = set()
        content._fill_related(related_user_ids, related_chat_ids, related_channel_ids, related_peer)
        await self._create_related(content, related_user_ids, related_chat_ids, related_channel_ids)

        return content

    @classmethod
    async def clone_forward_bulk(
            cls, contents: list[Self], fwd_headers: Sequence[models.MessageFwdHeader | None],
            post_infos: Sequence[models.ChannelPostInfo | None], media_group_ids: Sequence[int | None],
            related_peer: models.Peer, new_author: models.User | None = None, drop_captions: bool = False,
            drop_author: bool = False, is_forward: bool = False, no_forwards: bool = False,
            new_channel_author_id: int | None = None, channel_post: bool | None = None, post_author: str | None = None,
            anonymous: bool | None = None,
    ) -> list[Self]:
        new_contents = []
        internal_random_ids = []

        for content, fwd_header, post_info, media_group_id in zip(contents, fwd_headers, post_infos, media_group_ids):
            new_author_c = new_author
            new_channel_author_id_c = new_channel_author_id
            anonymous_c = anonymous
            channel_post_c = channel_post
            post_author_c = post_author

            if new_author_c is None and content.author is not None:
                new_author_c = content.author
            if new_channel_author_id_c is None and content.send_as_channel_id is not None:
                new_channel_author_id_c = content.send_as_channel_id

            if anonymous_c is None:
                anonymous_c = content.anonymous if not drop_author else None
            if channel_post_c is None:
                channel_post_c = content.channel_post if not drop_author else None
            if post_info is None:
                post_info = content.post_info if not drop_author else None
            if post_author_c is None:
                post_author_c = content.post_author if not drop_author else None

            internal_random_id = uuid4()
            internal_random_ids.append(internal_random_id)
            new_contents.append(models.MessageContent(
                message=content.message if content.media is None or not drop_captions else None,
                entities=content.entities if content.media is None or not drop_captions else None,
                date=content.date if not is_forward else datetime.now(UTC),
                edit_date=content.edit_date if not is_forward else None,
                type=content.type,
                author=new_author_c,
                media=content.media,
                fwd_header=fwd_header,
                media_group_id=media_group_id,
                channel_post=channel_post_c,
                post_author=post_author_c,
                post_info=post_info,
                anonymous=anonymous_c,
                no_forwards=no_forwards,
                via_bot=content.via_bot,
                send_as_channel_id=new_channel_author_id_c,
                internal_random_id=internal_random_id,
            ))

        await cls.bulk_create(new_contents)

        msg_id_by_random_id = {
            internal_random_id: content_id
            for content_id, internal_random_id in await cls.filter(
                internal_random_id__in=internal_random_ids,
            ).values_list("id", "internal_random_id")
        }

        await cls.filter(id__in=list(msg_id_by_random_id.values())).update(internal_random_id=None)

        related_to_create = []

        for content in new_contents:
            await asyncio.sleep(0)

            content.id = msg_id_by_random_id[content.internal_random_id]
            content._saved_in_db = True

            related_user_ids = set()
            related_chat_ids = set()
            related_channel_ids = set()
            content._fill_related(related_user_ids, related_chat_ids, related_channel_ids, related_peer)

            for related_user_id in related_user_ids:
                related_to_create.append(models.MessageRelated(message_id=content.id, user_id=related_user_id))
            for related_chat_id in related_chat_ids:
                related_to_create.append(models.MessageRelated(message_id=content.id, chat_id=related_chat_id))
            for related_channel_id in related_channel_ids:
                related_to_create.append(models.MessageRelated(message_id=content.id, channel_id=related_channel_id))

        if related_to_create:
            await models.MessageRelated.bulk_create(related_to_create)

        return new_contents

    async def create_fwd_header(
            self, ref: models.MessageRef, to_self: bool, discussion: bool = False,
    ) -> models.MessageFwdHeader:
        # TODO: pass prefetched privacy rules as an argument
        # TODO: handle send_as_channel authors

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
                # TODO: handle anonymous admins and "send_as_channel" in chats and channels
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
    async def create_fwd_header_bulk(
            cls, refs: list[models.MessageRef], user_id: int, to_self: bool,
    ) -> list[models.MessageFwdHeader]:
        if not refs:
            return []

        # TODO: pass prefetched privacy rules as an argument
        # TODO: handle send_as_channel authors

        fetch_privacy_rules_for = set()

        for ref in refs:
            if ref.content.fwd_header_id is None and not ref.content.channel_post:
                fetch_privacy_rules_for.add(ref.content.author_id)
            if to_self and ref.peer.type is PeerType.USER:
                fetch_privacy_rules_for.add(ref.peer.user_id)

        privacy_rules = await models.PrivacyRule.has_access_to_bulk(
            fetch_privacy_rules_for, user_id, [PrivacyRuleKeyType.FORWARDS]
        )

        fwd_headers = []
        internal_ids = []

        for ref in refs:
            content = ref.content

            if content.fwd_header is not None:
                from_user = content.fwd_header.from_user
                from_chat = content.fwd_header.from_chat
                from_channel = content.fwd_header.from_channel
                from_name = content.fwd_header.from_name
                channel_post_id = content.fwd_header.channel_post_id
                channel_post_author = content.fwd_header.channel_post_author
            else:
                from_user = None
                from_chat = None
                from_channel = None
                channel_post_id = None
                channel_post_author = None
                if content.channel_post:
                    from_channel = ref.peer.channel
                    from_name = from_channel.name
                    channel_post_id = ref.id
                    channel_post_author = content.post_author
                else:
                    # TODO: handle anonymous admins and "send_as_channel" in chats and channels
                    if privacy_rules[content.author_id][PrivacyRuleKeyType.FORWARDS]:
                        from_user = content.author
                    from_name = content.author.first_name

            saved_peer = ref.peer if to_self else None
            if saved_peer is not None and saved_peer.type is PeerType.USER:
                peer_ = ref.peer
                if not privacy_rules[peer_.user_id][PrivacyRuleKeyType.FORWARDS]:
                    saved_peer = None

            internal_random_id = uuid4()
            internal_ids.append(internal_random_id)
            fwd_headers.append(models.MessageFwdHeader(
                from_user=from_user,
                from_chat=from_chat,
                from_channel=from_channel,
                from_name=from_name,
                date=content.fwd_header.date if content.fwd_header else content.date,
                saved_out=True,

                channel_post_id=channel_post_id,
                channel_post_author=channel_post_author,

                saved_peer=saved_peer,
                saved_id=ref.id if to_self else None,
                saved_from=content.author if to_self else None,
                saved_name=content.author.first_name if to_self else None,
                saved_date=content.date if to_self else None,

                internal_random_id=internal_random_id,
            ))

        async with in_transaction():
            await models.MessageFwdHeader.bulk_create(fwd_headers)

            ids = {
                random_id: actual_id
                for actual_id, random_id in await models.MessageFwdHeader.filter(
                    internal_random_id__in=internal_ids,
                ).values_list("id", "internal_random_id")
            }

            for fwd_header in fwd_headers:
                fwd_header.id = ids[fwd_header.internal_random_id]
                fwd_header._saved_in_db = True

            await models.MessageFwdHeader.filter(id__in=list(ids.values())).update(internal_random_id=None)

        return fwd_headers

    @classmethod
    async def create_for_peer(cls, related_peer: models.Peer, **message_kwargs) -> Self:
        related_user_ids: set[int] = set()
        related_chat_ids: set[int] = set()
        related_channel_ids: set[int] = set()

        content = await MessageContent.create(**message_kwargs)

        content._fill_related(related_user_ids, related_chat_ids, related_channel_ids, related_peer)
        await cls._create_related(content, related_user_ids, related_chat_ids, related_channel_ids)

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

        if not self.channel_post and not self.anonymous and self.author_id is not None:
            user_ids.add(self.author_id)
        if self.send_as_channel_id is not None:
            channel_ids.add(self.send_as_channel_id)

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

    @staticmethod
    async def _create_related(
            message: MessageContent,
            users: Iterable[models.User | int],
            chats: Iterable[models.Chat | int],
            channels: Iterable[models.Channel | int],
    ) -> None:
        related_to_create = [
            *(
                models.MessageRelated(message=message, user_id=(rel.id if isinstance(rel, models.User) else rel))
                for rel in users
            ),
            *(
                models.MessageRelated(message=message, chat_id=(rel.id if isinstance(rel, models.Chat) else rel))
                for rel in chats
            ),
            *(
                models.MessageRelated(message=message, channel_id=(rel.id if isinstance(rel, models.Channel) else rel))
                for rel in channels
            ),
        ]

        if related_to_create:
            await models.MessageRelated.bulk_create(related_to_create)

    def cache_key(self) -> str:
        return f"message-content:{self.id}:{self.version}"
