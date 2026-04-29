from __future__ import annotations

from collections import defaultdict
from typing import TypeVar, Self, Iterable, cast, Sequence

from loguru import logger
from tortoise import fields, Model
from tortoise.expressions import Q, Subquery
from tortoise.functions import Count, Max, Coalesce

from piltover.cache import Cache
from piltover.db import models
from piltover.db.enums import MessageType, PeerType, READABLE_FILE_TYPES
from piltover.db.models.utils import NullableFKSetNull
from piltover.exceptions import ErrorRpc, Unreachable
from piltover.tl import MessageReplyHeader, MessageReactions, ReactionEmoji, ReactionCustomEmoji, ReactionCount, \
    MessageReplies as TLMessageReplies, PeerChannel, PeerUser
from piltover.tl.base import Message as TLMessageBase
from piltover.tl.base.internal import MessageToFormatRef
from piltover.tl.to_format import MessageToFormat, ChannelMessageToFormat
from piltover.tl.types.internal import ChannelMessageToFormatCommon

_T = TypeVar("_T")
BackwardO2OOrT = fields.BackwardOneToOneRelation[_T] | _T


def append_channel_min_message_id_to_query_maybe(
        peer: models.Peer | models.Channel, query: Q, participant: models.ChatParticipant | None = None,
        user: models.User | int | None = None,
) -> Q:
    user_id = user.id if isinstance(user, models.User) else user

    channel = None
    participant_user_id = None
    if isinstance(peer, models.Peer) and peer.type is PeerType.CHANNEL:
        channel = peer.channel
        participant_user_id = peer.owner_id
    elif isinstance(peer, models.Channel):
        channel = peer
        participant_user_id = user_id

    if channel is not None:
        if channel.min_available_id or channel.min_available_id_force:
            query &= Q(id__gte=max(channel.min_available_id or 0, channel.min_available_id_force or 0))
        if participant is not None and participant.min_message_id is not None:
            query &= Q(id__gte=participant.min_message_id)
        else:
            query &= Q(id__gte=Coalesce(
                Subquery(
                    models.ChatParticipant.get_or_none(
                        user_id=participant_user_id, channel=channel
                    ).values("min_message_id")
                ),
                0,
            ))

    return query


class MessageRef(Model):
    id: int = fields.BigIntField(primary_key=True)
    content: models.MessageContent = fields.ForeignKeyField("models.MessageContent")
    peer: models.Peer = fields.ForeignKeyField("models.Peer")
    random_id: int | None = fields.BigIntField(null=True, default=None, db_index=True)
    pinned: bool = fields.BooleanField(default=False)
    version: int = fields.IntField(default=0)
    from_scheduled: bool = fields.BooleanField(default=False)
    reply_to: models.MessageRef | None = NullableFKSetNull("models.MessageRef", related_name="reply")
    top_message: models.MessageRef | None = NullableFKSetNull("models.MessageRef", related_name="msg_top_message")
    discussion: models.MessageRef | None = NullableFKSetNull("models.MessageRef", related_name="msg_discussion_message")
    is_discussion: bool = fields.BooleanField(default=False)

    content_id: int
    peer_id: int
    reply_to_id: int | None
    top_message_id: int | None
    discussion_id: int | None

    taskiqscheduledmessages: BackwardO2OOrT[models.TaskIqScheduledMessage]

    PREFETCH_FIELDS_MIN = (
        "peer", "content", "content__media",
    )
    PREFETCH_FIELDS = (
        *PREFETCH_FIELDS_MIN, "content__media__file", "content__media__file__stickerset",
        "content__media__poll", "content__fwd_header", "content__fwd_header__saved_peer", "content__post_info",
        "content__via_bot", "peer__channel",
    )
    PREFETCH_MAYBECACHED = ("peer", "content", "peer__channel")
    _FETCH_CACHED_REFS = ("content__media", "content__media__file")
    _FETCH_CACHED_CONTENTS = (
        "content__media", "content__media__file", "content__media__file__stickerset", "content__media__poll",
        "content__media__poll__pollanswers", "content__post_info",
        "content__fwd_header", "content__fwd_header__saved_peer",
    )

    class Meta:
        unique_together = (
            ("peer", "content"),
            ("peer", "random_id"),
        )
        indexes = (
            ("peer_id", "pinned"),
        )

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(id={self.id}, peer={self.peer!r}, content={self.content!r})"

    def cache_key(self, user_id: int) -> str:
        return f"message-ref:{user_id}:{self.id}:{self.version}"

    @classmethod
    async def get_(
            cls, id_: int, peer: models.Peer, types: tuple[MessageType, ...] = (MessageType.REGULAR,),
            prefetch_all: bool = False, prefetch: tuple[str, ...] = (),
    ) -> Self | None:
        types_query = Q()
        for message_type in types:
            types_query |= Q(content__type=message_type)

        query = peer.q_this_or_channel() & types_query & Q(id=id_)
        query = append_channel_min_message_id_to_query_maybe(peer, query)

        return await cls.get_or_none(query).select_related(
            *(cls.PREFETCH_FIELDS if prefetch_all else cls.PREFETCH_FIELDS_MIN),
            *prefetch,
        )

    @classmethod
    async def get_many(
            cls, ids: list[int], peer: models.Peer, prefetch_all: bool = False, prefetch_fields: tuple[str, ...] = ()
                       ) -> list[Self]:
        query = peer.q_this_or_channel() & Q(id__in=ids, content__type=MessageType.REGULAR)
        query = append_channel_min_message_id_to_query_maybe(peer, query)

        return await cls.filter(query).select_related(
            *(cls.PREFETCH_FIELDS if prefetch_all else cls.PREFETCH_FIELDS_MIN),
            *prefetch_fields,
        )

    def _to_tl_ref(
            self, out: bool, mentioned: bool, media_unread: bool,
    ) -> MessageToFormatRef:
        return MessageToFormatRef(
            id=self.id,
            pinned=self.pinned,
            peer_id=self.peer.to_tl(),
            out=out,
            reply_to=self.make_reply_to_header(),
            mentioned=mentioned,
            media_unread=media_unread,
            from_scheduled=self.from_scheduled or self.content.scheduled_date,
        )

    async def to_tl_ref(self, user_id: int) -> MessageToFormatRef:
        cache_key = self.cache_key(user_id)
        if (cached := await Cache.obj.get(cache_key)) is not None:
            return cached

        mention_read = await models.MessageMention.filter(
            user_id=user_id, message_id=self.content_id
        ).first().values_list("read", flat=True)
        mentioned = mention_read is not None
        if not mentioned:
            mention_read = True

        media_unread = False
        if self.content.media \
                and self.content.media.file \
                and self.content.media.file.type in READABLE_FILE_TYPES:
            media_unread = not await models.MessageMediaRead.filter(user_id=user_id, message=self).exists()

        message = self._to_tl_ref(
            out=user_id == self.content.author_id,
            mentioned=mentioned,
            media_unread=media_unread if media_unread else not mention_read,
        )

        await Cache.obj.set(cache_key, message)
        return message

    async def get_mentioned_media_unread(self, user_id: int) -> tuple[bool, bool]:
        ref = await self.to_tl_ref(user_id)
        return ref.mentioned, ref.media_unread

    def to_tl_common_channel(self) -> ChannelMessageToFormatCommon:
        return ChannelMessageToFormatCommon(
            author_id=self.content.author_id,
            id=self.id,
            channel_id=self.peer.channel_id,
            from_scheduled=self.from_scheduled or self.content.scheduled_date,
            pinned=self.pinned,
            reply_to=self.make_reply_to_header(),
        )

    async def to_tl(self, user: models.User | int, with_reactions: bool = True) -> MessageToFormat:
        user_id = user.id if isinstance(user, models.User) else user

        reactions = None
        if with_reactions and self.content.type is MessageType.REGULAR:
            reactions = await self.to_tl_reactions(user_id)

        return MessageToFormat(
            ref=await self.to_tl_ref(user_id),
            content=await self.content.to_tl_content(),
            reactions=reactions,
            replies=await self.to_tl_replies(),
        )

    @classmethod
    async def to_tl_ref_bulk(cls, refs: list[models.MessageRef], user_id: int) -> list[TLMessageBase]:
        if not refs:
            return []

        cache_keys = [ref.cache_key(user_id) for ref in refs]
        cached = await Cache.obj.multi_get(cache_keys)

        message_content_ids = {
            ref.content.id
            for ref, cached_ref in zip(refs, cached)
            if cached_ref is None and not ref.content.is_service()
        }

        mentioned: dict[int, bool] = {}

        if message_content_ids:
            mentions_info = await models.MessageMention.filter(
                user_id=user_id, message_id__in=message_content_ids,
            ).values_list("message_id", "read")
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
                user_id=user_id, message_id__in=valid_media_ref_ids,
            ).values_list("message_id", flat=True))
        else:
            media_read = set()

        to_cache = []

        result = []
        for ref, cached_ref in zip(refs, cached):
            if cached_ref is not None:
                result.append(cached_ref)
                continue

            result.append(ref._to_tl_ref(
                out=user_id == ref.content.author_id,
                mentioned=ref.content_id in mentioned,
                media_unread=ref.id not in media_read and not mentioned.get(ref.content_id, True),
            ))

            to_cache.append((ref.cache_key(user_id), result[-1]))

        if to_cache:
            await Cache.obj.multi_set(to_cache)

        return result

    @classmethod
    async def get_mentioned_media_unread_bulk(cls, messages: list[MessageRef], user_id: int) -> list[tuple[bool, bool]]:
        refs = await cls.to_tl_ref_bulk(messages, user_id)
        return [(ref.mentioned, ref.media_unread) for ref in refs]

    @classmethod
    async def to_tl_bulk(
            cls, messages: list[MessageRef], user: models.User | int, with_reactions: bool = True,
    ) -> list[TLMessageBase]:
        user_id = user.id if isinstance(user, models.User) else user
        raw_contents = [ref.content for ref in messages]

        reactionss: list[MessageReactions | None] = [None for _ in messages]
        if with_reactions:
            reactionss = await MessageRef.to_tl_reactions_bulk(messages, user_id)

        refs = await MessageRef.to_tl_ref_bulk(messages, user_id)
        contents = await models.MessageContent.to_tl_content_bulk(raw_contents)
        repliess = await MessageRef.to_tl_replies_bulk(messages)

        if len(contents) != len(refs):
            raise Unreachable(f"len(contents) != len(refs), {len(contents)} != {len(refs)}")

        return [
            MessageToFormat(ref=ref, content=content, reactions=reactions, replies=replies)
            for ref, content, reactions, replies in zip(refs, contents, reactionss, repliess)
        ]

    @classmethod
    async def to_tl_channel_bulk(cls, messages: list[MessageRef]) -> list[ChannelMessageToFormat]:
        raw_contents = [ref.content for ref in messages]

        commons = [ref.to_tl_common_channel() for ref in messages]
        contents = await models.MessageContent.to_tl_content_bulk(raw_contents)
        repliess = await MessageRef.to_tl_replies_bulk(messages)

        if len(contents) != len(commons):
            raise Unreachable(f"len(contents) != len(commons), {len(contents)} != {len(commons)}")

        return [
            ChannelMessageToFormat(common=common, content=content, replies=replies)
            for common, content, replies in zip(commons, contents, repliess)
        ]

    async def to_tl_maybecached(self, user_id: int, with_reactions: bool = True) -> TLMessageBase:
        if self.discussion_id is not None or self.is_discussion:
            ref, content, replies = await Cache.obj.multi_get([
                self.cache_key(user_id), self.content.cache_key(), self.cache_key_replies(),
            ])
        else:
            ref, content = await Cache.obj.multi_get([self.cache_key(user_id), self.content.cache_key()])
            replies = None
        reactions = None

        need_fetch = set()
        if ref is None:
            need_fetch.update(self._FETCH_CACHED_REFS)
        if content is None:
            need_fetch.update(self._FETCH_CACHED_CONTENTS)

        if need_fetch:
            await self.fetch_related(*need_fetch)

        if ref is None:
            ref = await self.to_tl_ref(user_id)
        if content is None:
            content = await self.content.to_tl_content()
        if with_reactions:
            reactions = await self.to_tl_reactions(user_id)
        if replies is None:
            replies = await self.to_tl_replies()

        return MessageToFormat(ref=ref, content=content, reactions=reactions, replies=replies)

    @classmethod
    async def to_tl_bulk_maybecached(
            cls, refs: list[MessageRef], user_id: int, with_reactions: bool = True,
    ) -> list[TLMessageBase]:
        if not refs:
            return []

        cache_keys = [ref.cache_key(user_id) for ref in refs] + [ref.content.cache_key() for ref in refs]

        all_cached = await Cache.obj.multi_get(cache_keys)
        refs_cached = all_cached[:len(refs)]
        contents_cached = all_cached[len(refs):len(refs)*2]

        need_fetch_refs = []
        need_fetch_contents = []

        for ref, ref_cached, content_cached in zip(refs, refs_cached, contents_cached):
            if content_cached is None:
                need_fetch_contents.append(ref)
            elif ref_cached is None:
                need_fetch_refs.append(ref)

        if need_fetch_refs:
            await MessageRef.fetch_for_list(need_fetch_refs, *cls._FETCH_CACHED_REFS)
        if need_fetch_contents:
            await MessageRef.fetch_for_list(need_fetch_contents, *cls._FETCH_CACHED_CONTENTS)

        refs_tl = await cls.to_tl_ref_bulk([
            ref for ref, cached in zip(refs, refs_cached) if cached is None
        ], user_id)
        refs_tl.reverse()
        contents_tl = await models.MessageContent.to_tl_content_bulk([
            ref.content for ref, cached in zip(refs, contents_cached) if cached is None
        ])
        contents_tl.reverse()
        if with_reactions:
            reactionss_tl = await cls.to_tl_reactions_bulk(refs, user_id)
        else:
            reactionss_tl = [None] * len(refs)
        replies_tl = await cls.to_tl_replies_bulk(refs)

        results = []
        zipped = zip(refs, refs_cached, contents_cached, reactionss_tl, replies_tl)
        for ref, result_ref, result_content, result_reactions, result_replies in zipped:
            if result_ref is None:
                result_ref = refs_tl.pop()
            if result_content is None:
                result_content = contents_tl.pop()

            results.append(MessageToFormat(
                ref=result_ref,
                content=result_content,
                reactions=result_reactions,
                replies=result_replies,
            ))

        return results

    async def send_scheduled(self, opposite: bool = True) -> dict[models.Peer, Self]:
        peers = [self.peer]
        if opposite and self.peer.type is not PeerType.CHANNEL:
            peers.extend(await self.peer.get_opposite())
        elif opposite and self.peer.type is PeerType.CHANNEL:
            peers = [await models.Peer.get_or_none(owner=None, channel_id=self.peer.channel_id, type=PeerType.CHANNEL)]

        if self.reply_to_id:
            replies = {
                ref.peer_id: ref
                for ref in await MessageRef.filter(content_id=self.reply_to.content_id)
            }
        else:
            replies = {}

        messages: dict[models.Peer, MessageRef] = {}

        content = await self.content.clone_scheduled()

        for to_peer in peers:
            # TODO: probably create in bulk too?
            messages[to_peer] = await MessageRef.create(
                peer=to_peer,
                content=content,
                from_scheduled=to_peer == self.peer,
                reply_to=replies.get(to_peer.id),
            )

        await models.Dialog.create_or_unhide_bulk(peers)
        return messages

    async def clone_ref_for_peer(self, peer: models.Peer) -> Self:
        return await models.MessageRef.create(
            peer=peer,
            content=self.content,
            pinned=self.pinned,
        )

    async def forward_for_peers(
            self, to_peer: models.Peer, peers: Iterable[models.Peer], new_author: models.User | None = None,
            random_id: int | None = None,
            # TODO: make required
            fwd_header: models.MessageFwdHeader | None = None,
            reply_to_content_id: int | None = None, drop_captions: bool = False, media_group_id: int | None = None,
            drop_author: bool = False, is_forward: bool = False, no_forwards: bool = False, pinned: bool | None = None,
            is_discussion: bool = False, channel_post: bool | None = None,
            post_info: models.ChannelPostInfo | None = None, post_author: str | None = None,
            anonymous: bool | None = None, new_channel_author_id: int | None = None,
    ) -> list[Self]:
        if not peers:
            return []

        content = await self.content.clone_forward(
            related_peer=to_peer,
            new_author=new_author,
            fwd_header=fwd_header,
            drop_captions=drop_captions,
            media_group_id=media_group_id,
            drop_author=drop_author,
            is_forward=is_forward,
            no_forwards=no_forwards,
            channel_post=channel_post,
            post_info=post_info,
            post_author=post_author,
            anonymous=anonymous,
            new_channel_author_id=new_channel_author_id,
        )

        peer_ids = [peer.id for peer in peers]

        replies: dict[int, int]
        if reply_to_content_id:
            replies = {
                peer_id: ref_id
                for ref_id, peer_id in await MessageRef.filter(
                    peer_id__in=peer_ids, content_id=reply_to_content_id,
                ).values_list("id", "peer_id")
            }
        else:
            replies = {}

        messages = []
        for peer in peers:
            messages.append(models.MessageRef(
                peer=peer,
                content=content,
                pinned=self.pinned if pinned is None else pinned,
                random_id=random_id if peer == to_peer else None,
                reply_to_id=replies.get(peer.id),
                is_discussion=is_discussion,
            ))

        await MessageRef.bulk_create(messages)

        ref_ids_by_peer_ids = {
            peer_id: ref_id
            for ref_id, peer_id in await MessageRef.filter(
                peer_id__in=peer_ids, content_id=content.id,
            ).values_list("id", "peer_id")
        }

        for message in messages:
            message.id = ref_ids_by_peer_ids[message.peer.id]
            message._saved_in_db = True

        return messages

    @classmethod
    async def forward_for_peers_bulk(
            cls,
            new_contents: list[models.MessageContent],
            to_peer: models.Peer,
            peers: Iterable[models.Peer],
            random_ids: Sequence[int | None],
            reply_to_content_ids: Sequence[int | None],
            pinned: Sequence[bool],
            is_discussion: Sequence[bool],
    ) -> list[Self]:
        if not peers or not new_contents:
            return []

        messages = []
        for content, random_id, pinned_ in zip(new_contents, random_ids, pinned):
            for peer in peers:
                # TODO: fill reply_to_id
                messages.append(models.MessageRef(
                    peer=peer,
                    content=content,
                    pinned=pinned_,
                    random_id=random_id if peer == to_peer else None,
                    is_discussion=is_discussion,
                ))

        await MessageRef.bulk_create(messages)

        ref_ids_by_peer_ids = {
            (peer_id, content_id): ref_id
            for ref_id, peer_id, content_id in await MessageRef.filter(
                peer_id__in=[peer.id for peer in peers], content_id__in=[content.id for content in new_contents],
            ).values_list("id", "peer_id", "content_id")
        }

        replies_by_content_id = {
            content.id: reply_to_content_id
            for content, reply_to_content_id in zip(new_contents, reply_to_content_ids)
            if reply_to_content_id is not None
        }

        to_update = []

        for message in messages:
            message.id = ref_ids_by_peer_ids[(message.peer.id, message.content.id)]
            message._saved_in_db = True

            if message.content.id in replies_by_content_id:
                reply_to_ref_id = ref_ids_by_peer_ids.get(
                    (message.peer.id, replies_by_content_id[message.content.id])
                )
                if reply_to_ref_id:
                    message.reply_to_id = reply_to_ref_id
                    to_update.append(message)

        if to_update:
            await cls.bulk_update(to_update, ["reply_to_id"])

        return messages

    async def create_fwd_header(self, to_self: bool, discussion: bool = False) -> models.MessageFwdHeader:
        return await self.content.create_fwd_header(self, to_self, discussion)

    @classmethod
    async def create_fwd_header_bulk(
            cls, refs: list[MessageRef], user_id: int, to_self: bool
    ) -> list[models.MessageFwdHeader]:
        return await models.MessageContent.create_fwd_header_bulk(refs, user_id, to_self)

    @classmethod
    async def create_for_peer(
            cls, peer: models.Peer, author: models.User | int, random_id: int | None = None,
            opposite: bool = True, unhide_dialog: bool = True, reply_to: MessageRef | None = None,
            top_message: MessageRef | None = None,
            **message_kwargs,
    ) -> dict[models.Peer, Self]:
        # TODO: create composite index with random_id, peer (and user so in channels it will work properly?) \
        #  and rely on database error
        if random_id is not None and await cls.filter(peer=peer, random_id=random_id).exists():
            raise ErrorRpc(error_code=500, error_message="RANDOM_ID_DUPLICATE")

        author_kwargs = {}
        if isinstance(author, models.User):
            author_kwargs["author"] = author
        elif isinstance(author, int):
            author_kwargs["author_id"] = author
        else:
            raise ValueError(f"Expected User or int, got {author}")

        content = await models.MessageContent.create_for_peer(
            related_peer=peer,
            **author_kwargs,
            **message_kwargs,
        )

        peers = [peer]
        if opposite and peer.type is not PeerType.CHANNEL:
            peers.extend(await peer.get_opposite())
        elif opposite and peer.type is PeerType.CHANNEL:
            peers = [await models.Peer.get_or_none(owner=None, channel=peer.channel, type=PeerType.CHANNEL)]

        if reply_to is not None:
            replies = {
                ref.peer_id: ref
                for ref in await MessageRef.filter(
                    peer_id__in=[peer.id for peer in peers], content_id=reply_to.content_id,
                )
            }
        else:
            replies = {}

        refs_to_create = [
            cls(
                peer=to_peer,
                content=content,
                random_id=random_id if to_peer == peer or to_peer.type is PeerType.CHANNEL else None,
                reply_to=replies.get(to_peer.id),
                top_message=top_message,
            )
            for to_peer in peers
        ]

        if refs_to_create:
            await cls.bulk_create(refs_to_create)

        refs = await cls.filter(content=content)

        peer_by_id = {peer.id: peer for peer in peers}
        messages: dict[models.Peer, MessageRef] = {}

        for ref in refs:
            ref.peer = peer_by_id[ref.peer_id]
            ref.content = content
            messages[ref.peer] = ref

        if unhide_dialog:
            await models.Dialog.create_or_unhide_bulk(peers)

        return messages

    async def get_for_user(self, for_user: models.User) -> Self | None:
        if self.peer.type is PeerType.CHANNEL:
            return self

        if self.peer.type is PeerType.SELF:
            if for_user.id == self.peer.owner_id:
                return self
            return None

        if self.peer.type is PeerType.USER:
            return await MessageRef.get_or_none(
                peer__owner=for_user, peer__user=self.peer.owner_id, content_id=self.content_id,
            ).select_related(*self.PREFETCH_FIELDS_MIN)

        if self.peer.type is PeerType.CHAT:
            return await MessageRef.get_or_none(
                peer__owner=for_user, peer__chat_id=self.peer.chat_id, content_id=self.content_id,
            ).select_related(*self.PREFETCH_FIELDS_MIN)

        raise Unreachable

    def peer_key(self) -> tuple[PeerType, int]:
        if self.peer.type in (PeerType.SELF, PeerType.USER):
            peer_id = self.peer.user_id
        elif self.peer.type is PeerType.CHAT:
            peer_id = self.peer.chat_id
        elif self.peer.type is PeerType.CHANNEL:
            peer_id = self.peer.channel_id
        else:
            raise Unreachable

        return self.peer.type, peer_id

    def make_reply_to_header(self) -> MessageReplyHeader | None:
        if self.reply_to_id is None and self.top_message_id is None:
            return None

        return MessageReplyHeader(
            reply_to_msg_id=self.reply_to_id,
            reply_to_top_id=self.top_message_id,
        )

    async def _get_user_reaction(self, user_id: int) -> tuple[int, None] | tuple[None, int] | None:
        return cast(
            tuple[int, None] | tuple[None, int] | None,
            await models.MessageReaction.get_or_none(
                user_id=user_id, message_id=self.content_id,
            ).values_list("reaction_id", "custom_emoji_id")
        )

    @staticmethod
    async def _get_user_reaction_bulk(
            content_ids: list[int], user_id: int,
    ) -> dict[int, tuple[int, None] | tuple[None, int]]:
        user_reactions = {}
        for message_id, reaction_id, custom_emoji_id in await models.MessageReaction.filter(
                user_id=user_id, message_id__in=content_ids,
        ).values_list("message_id", "reaction_id", "custom_emoji_id"):
            user_reactions[message_id] = reaction_id, custom_emoji_id
        return user_reactions

    async def to_tl_reactions(self, user_id: int) -> MessageReactions | None:
        if self.content.type is not MessageType.REGULAR:
            return None

        user_reaction = await self._get_user_reaction(user_id)
        if user_reaction:
            user_reaction_id, user_custom_emoji_id = user_reaction
            min_ = False
        else:
            user_reaction_id = user_custom_emoji_id = None
            min_ = True

        if self.content.author_id == user_id:
            cache_key = self.cache_key_reactions_author(user_id)
        else:
            cache_key = self.cache_key_reactions(user_reaction_id, user_custom_emoji_id)

        if (cached := await Cache.obj.get(cache_key)) is not None:
            return cached

        reactions = await models.MessageReaction \
            .annotate(msg_count=Count("id")) \
            .filter(message_id=self.content_id) \
            .group_by("reaction__id", "custom_emoji_id") \
            .select_related("reaction") \
            .values_list("reaction__id", "custom_emoji_id", "reaction__reaction", "msg_count")

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

        can_see_list = (
                self.peer.type in (PeerType.SELF, PeerType.USER, PeerType.CHAT)
                or self.peer.type is PeerType.CHANNEL and self.peer.channel.supergroup
        )

        recent_reactions = None
        if can_see_list:
            if self.content.author_id == user_id:
                is_unread = self.content.author_reactions_unread
            else:
                is_unread = False

            recent_reactions = []

            for recent in await models.MessageReaction.filter(
                    message_id=self.content_id,
            ).order_by("-date").limit(5).select_related("reaction"):
                recent_reactions.append(recent.to_tl_peer_reaction(user_id, is_unread))

        result = MessageReactions(
            min=min_,
            can_see_list=can_see_list,
            results=results,
            recent_reactions=recent_reactions,
        )

        await Cache.obj.set(cache_key, result)

        return result

    @classmethod
    async def to_tl_reactions_bulk(cls, messages: list[MessageRef], user_id: int) -> list[MessageReactions]:
        if not messages:
            return []

        content_ids = [ref.content_id for ref in messages if ref.content.type is MessageType.REGULAR]

        user_reactions = await cls._get_user_reaction_bulk(content_ids, user_id)

        cache_keys = []
        for ref in messages:
            if ref.content.author_id == user_id:
                cache_keys.append(ref.cache_key_reactions_author(user_id))
            else:
                if ref.content_id in user_reactions:
                    cache_keys.append(ref.cache_key_reactions(*user_reactions[ref.content_id]))
                else:
                    cache_keys.append(ref.cache_key_reactions(None, None))

        cached_reactions = await Cache.obj.multi_get(cache_keys)

        not_cached_ids = [
            ref.content_id
            for ref, cached in zip(messages, cached_reactions)
            if cached is None and ref.content.type is MessageType.REGULAR
        ]
        if not_cached_ids:
            reactions_raw = await models.MessageReaction \
                .annotate(msg_count=Count("id")) \
                .filter(message_id__in=not_cached_ids) \
                .group_by("message_id", "reaction__id", "custom_emoji_id") \
                .select_related("reaction") \
                .values_list("message_id", "reaction__id", "custom_emoji_id", "reaction__reaction", "msg_count")
        else:
            reactions_raw = []

        reactions = defaultdict(list)
        for message_id, reaction_id, custom_emoji_id, reaction_emoji, msg_count in reactions_raw:
            reactions[message_id].append((reaction_id, custom_emoji_id, reaction_emoji, msg_count))

        results = []
        to_cache = []

        for ref, cached, cache_key in zip(messages, cached_reactions, cache_keys):
            if ref.content.type is not MessageType.REGULAR:
                results.append(None)
                continue
            if cached is not None:
                results.append(cached)
                continue

            reaction_results = []
            for reaction_id, custom_emoji_id, reaction_emoji, msg_count in reactions[ref.content_id]:
                if reaction_id is not None:
                    reaction = ReactionEmoji(emoticon=reaction_emoji)
                elif custom_emoji_id is not None:
                    reaction = ReactionCustomEmoji(document_id=custom_emoji_id)
                else:
                    raise Unreachable

                reaction_results.append(ReactionCount(
                    chosen_order=1 if (reaction_id, custom_emoji_id) == user_reactions.get(ref.content_id) else None,
                    reaction=reaction,
                    count=msg_count,
                ))

            can_see_list = (
                    ref.peer.type in (PeerType.SELF, PeerType.USER, PeerType.CHAT)
                    or ref.peer.type is PeerType.CHANNEL and ref.peer.channel.supergroup
            )

            recent_reactions = None
            if can_see_list:
                # TODO: do this outside the loop
                if ref.content.author_id == user_id:
                    is_unread = ref.content.author_reactions_unread
                else:
                    is_unread = False

                recent_reactions = []
                for recent in await models.MessageReaction.filter(
                        message_id=ref.content_id,
                ).order_by("-date").limit(5).select_related("reaction"):
                    recent_reactions.append(recent.to_tl_peer_reaction(user_id, is_unread))

            results.append(MessageReactions(
                min=ref.content_id not in user_reactions and ref.content.author_id != user_id,
                can_see_list=can_see_list,
                results=reaction_results,
                recent_reactions=recent_reactions,
            ))
            to_cache.append((cache_key, results[-1]))

        if to_cache:
            await Cache.obj.multi_set(to_cache)

        return results

    def cache_key_reactions_author(self, user_id: int) -> str:
        return f"message-reactions:{self.content_id}:a{user_id}:{self.content.reactions_version}"

    def cache_key_reactions(self, reaction: int | None, custom_emoji: int | None) -> str:
        return (
            f"message-reactions:"
            f"{self.content_id}:"
            f"r{reaction or 0}-{custom_emoji or 0}:"
            f"{self.content.reactions_version}"
        )

    async def _get_recent_repliers(self) -> list[...] | None:
        query = Q(reply_to_id=self.discussion_id, top_message_id=self.discussion_id, join_type=Q.OR)
        recent_replies = await MessageRef.filter(query).order_by("-id").limit(5).distinct().values_list(
            "content__author_id", "content__anonymous", "content__send_as_channel_id",
        )

        recent_repliers = []
        for user_id, anon, as_channel_id in recent_replies:
            if as_channel_id:
                recent_repliers.append(PeerChannel(channel_id=models.Channel.make_id_from(as_channel_id)))
            elif anon and self.peer.type is PeerType.CHANNEL:
                channel_id = self.peer.channel_id
                recent_repliers.append(PeerChannel(channel_id=models.Channel.make_id_from(channel_id)))
            elif not anon:
                recent_repliers.append(PeerUser(user_id=user_id))
            else:
                logger.warning(f"What: ref {self.id}; {user_id=}, {anon=}, {as_channel_id=}")

        return recent_repliers or None

    async def to_tl_replies(self, with_recent: bool = False) -> TLMessageReplies | None:
        if not self.is_discussion and self.discussion_id is None:
            return None

        cache_key = self.cache_key_replies()
        if (cached := await Cache.obj.get(cache_key)) is not None:
            return cached

        replies = None
        if self.is_discussion:
            query = Q(reply_to_id=self.id, top_message_id=self.id, join_type=Q.OR)
            replies_info = await models.MessageRef.filter(query).annotate(
                count=Count("id"), max_id=Max("id")
            ).first().values_list("count", "max_id")
            if replies_info:
                replies_count, max_id = replies_info
            else:
                replies_count = 0
                max_id = None

            replies = TLMessageReplies(
                replies=replies_count,
                replies_pts=0,
                max_id=max_id,
            )
        elif self.discussion_id is not None:
            query = Q(reply_to_id=self.discussion_id, top_message_id=self.discussion_id, join_type=Q.OR)
            replies_info = await models.MessageRef.filter(query).annotate(
                count=Count("id"), max_id=Max("id"),
            ).first().values_list("count", "max_id")
            if replies_info:
                replies_count, max_id = replies_info
            else:
                replies_count = 0
                max_id = None

            discussion_channel_id = cast(
                int | None,
                await models.MessageRef.get(id=self.discussion_id).values_list("peer__channel_id", flat=True)
            )

            recent_repliers = None
            if with_recent:
                recent_repliers = await self._get_recent_repliers()

            replies = TLMessageReplies(
                replies=replies_count,
                replies_pts=0,
                comments=True,
                channel_id=models.Channel.make_id_from(discussion_channel_id) if discussion_channel_id else None,
                max_id=max_id,
                recent_repliers=recent_repliers or None,
            )

        await Cache.obj.set(cache_key, replies)

        return replies

    @classmethod
    async def to_tl_replies_bulk(
            cls, refs: list[MessageRef], with_recent: bool = False,
    ) -> list[TLMessageReplies | None]:
        cache_keys = [
            ref.cache_key_replies()
            for ref in refs
            if ref.is_discussion or ref.discussion_id is not None
        ]

        if not cache_keys:
            return [None] * len(refs)

        cached_replies = await Cache.obj.multi_get(cache_keys)

        ids_to_get = set()
        channel_ids_to_get = set()
        cache_idx = 0
        for ref in refs:
            if not ref.is_discussion and ref.discussion_id is None:
                continue
            cached = cached_replies[cache_idx]
            cache_idx += 1
            if cached is not None:
                continue
            if ref.is_discussion:
                ids_to_get.add(ref.id)
            elif ref.discussion_id is not None:
                ids_to_get.add(ref.discussion_id)
                channel_ids_to_get.add(ref.discussion_id)
            else:
                raise Unreachable

        replies_stats = {
            top_msg_id: (count, max_id)
            for top_msg_id, count, max_id in await models.MessageRef.filter(
                top_message_id__in=ids_to_get,
            ).annotate(
                count=Count("id"), max_id=Max("id"),
            ).group_by(
                "top_message_id"
            ).values_list(
                "top_message_id", "count", "max_id",
            )
        }

        discussion_channel_ids = {
            msg_id: channel_id
            for msg_id, channel_id in await models.MessageRef.filter(
                id__in=channel_ids_to_get,
            ).values_list("id", "peer__channel_id")
        }

        to_cache = []
        replies = []
        cache_idx = 0
        for ref in refs:
            if not ref.is_discussion and ref.discussion_id is None:
                replies.append(None)
                continue
            cache_key = cache_keys[cache_idx]
            cached = cached_replies[cache_idx]
            cache_idx += 1
            if cached is not None:
                replies.append(cached)
                continue

            if ref.is_discussion:
                replies_count, max_id = replies_stats.get(ref.id, (0, None))
                replies_info = TLMessageReplies(
                    replies=replies_count,
                    replies_pts=0,
                    max_id=max_id,
                )
            elif ref.discussion_id is not None:
                replies_count, max_id = replies_stats.get(ref.discussion_id, (0, None))
                discussion_channel_id = discussion_channel_ids.get(ref.discussion_id)

                recent_repliers = None
                if with_recent:
                    recent_repliers = await ref._get_recent_repliers()

                replies_info = TLMessageReplies(
                    replies=replies_count,
                    replies_pts=0,
                    comments=True,
                    channel_id=models.Channel.make_id_from(discussion_channel_id) if discussion_channel_id else None,
                    max_id=max_id,
                    recent_repliers=recent_repliers,
                )
            else:
                raise Unreachable

            replies.append(replies_info)
            to_cache.append((cache_key, replies_info))

        if to_cache:
            await Cache.obj.multi_set(to_cache)

        return replies

    def cache_key_replies(self) -> str:
        return f"message-replies:{self.content_id}:{self.content.replies_version}"
