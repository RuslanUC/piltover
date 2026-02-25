from __future__ import annotations

from collections import defaultdict
from typing import TypeVar, Self, Iterable

from tortoise import fields, Model
from tortoise.expressions import Q
from tortoise.functions import Count

from piltover.cache import Cache
from piltover.db import models
from piltover.db.enums import MessageType, PeerType, READABLE_FILE_TYPES
from piltover.db.models.utils import Missing, MISSING, NullableFKSetNull
from piltover.exceptions import ErrorRpc, Unreachable
from piltover.tl import MessageReplyHeader, MessageReactions, ReactionEmoji, ReactionCustomEmoji, ReactionCount
from piltover.tl.base import Message as TLMessageBase
from piltover.tl.base.internal import MessageToFormatRef
from piltover.tl.to_format import MessageToFormat

_T = TypeVar("_T")
BackwardO2OOrT = fields.BackwardOneToOneRelation[_T] | _T


async def append_channel_min_message_id_to_query_maybe(
        peer: models.Peer, query: Q, participant: models.ChatParticipant | None = None,
) -> Q:
    if isinstance(peer, models.Peer) and peer.type is PeerType.CHANNEL:
        if participant is None:
            participant = await peer.channel.get_participant(peer.owner)
        if (channel_min_id := peer.channel.min_id(participant)) is not None:
            query &= Q(id__gte=channel_min_id)
    return query


class MessageRef(Model):
    id: int = fields.BigIntField(pk=True)
    content: models.MessageContent = fields.ForeignKeyField("models.MessageContent")
    peer: models.Peer = fields.ForeignKeyField("models.Peer")
    random_id: int | None = fields.BigIntField(null=True, default=None)
    pinned: bool = fields.BooleanField(default=False)
    version: int = fields.IntField(default=0)
    from_scheduled: bool = fields.BooleanField(default=False)
    reply_to: models.MessageRef | None = NullableFKSetNull("models.MessageRef", related_name="reply")
    top_message: models.MessageRef | None = NullableFKSetNull("models.MessageRef", related_name="msg_top_message")

    content_id: int
    peer_id: int
    reply_to_id: int | None
    top_message_id: int | None

    taskiqscheduledmessages: BackwardO2OOrT[models.TaskIqScheduledMessage]

    PREFETCH_FIELDS_MIN = (
        "peer", "content", "content__author", "content__media",
    )
    PREFETCH_FIELDS = (
        *PREFETCH_FIELDS_MIN, "peer__owner", "content__media__file", "content__media__file__stickerset",
        "content__media__poll", "content__fwd_header", "content__fwd_header__saved_peer", "content__post_info",
        "content__via_bot", "content__comments_info",
    )
    _PREFETCH_ALL_TOP_FIELDS = (
        "peer", "content__author", "content__media", "content__fwd_header", "reply_to",
        "content__via_bot",
    )

    class Meta:
        unique_together = (
            ("peer", "content"),
            ("peer", "random_id"),
        )

    def cache_key(self, user_id: int) -> str:
        return f"message-ref:{user_id}:{self.id}:{self.version}"

    @classmethod
    async def get_(
            cls, id_: int, peer: models.Peer, types: tuple[MessageType, ...] = (MessageType.REGULAR,),
            prefetch_all: bool = False,
    ) -> Self | None:
        types_query = Q()
        for message_type in types:
            types_query |= Q(content__type=message_type)

        query = peer.q_this_or_channel() & types_query & Q(id=id_)
        query = await append_channel_min_message_id_to_query_maybe(peer, query)

        return await cls.get_or_none(query).select_related(
            *(cls.PREFETCH_FIELDS if prefetch_all else cls.PREFETCH_FIELDS_MIN)
        )

    @classmethod
    async def get_many(cls, ids: list[int], peer: models.Peer, prefetch_all: bool = False) -> list[Self]:
        query = peer.q_this_or_channel() & Q(id__in=ids, content__type=MessageType.REGULAR)
        query = await append_channel_min_message_id_to_query_maybe(peer, query)

        return await cls.filter(query).select_related(
            *(cls.PREFETCH_FIELDS if prefetch_all else cls.PREFETCH_FIELDS_MIN)
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

    async def to_tl_ref(self, user: models.User) -> MessageToFormatRef:
        cache_key = self.cache_key(user.id)
        if (cached := await Cache.obj.get(cache_key)) is not None:
            return cached

        mention_read = await models.MessageMention.filter(
            user=user, message_id=self.content_id
        ).first().values_list("read", flat=True)
        mentioned = mention_read is not None
        if not mentioned:
            mention_read = True

        media_unread = False
        if self.content.media \
                and self.content.media.file \
                and self.content.media.file.type in READABLE_FILE_TYPES:
            media_unread = not await models.MessageMediaRead.filter(user_id=user.id, message=self).exists()

        message = self._to_tl_ref(
            out=user.id == self.content.author_id,
            mentioned=mentioned,
            media_unread=media_unread if media_unread else not mention_read,
        )

        await Cache.obj.set(cache_key, message)
        return message

    async def to_tl(self, user: models.User, with_reactions: bool = True) -> TLMessageBase:
        reactions = None
        if with_reactions and self.content.type is MessageType.REGULAR:
            reactions = await self.to_tl_reactions(user)

        return MessageToFormat(
            ref=await self.to_tl_ref(user),
            content=await self.content.to_tl_content(),
            reactions=reactions,
        )

    @classmethod
    async def to_tl_ref_bulk(cls, refs: list[models.MessageRef], user_id: int) -> list[TLMessageBase]:
        cached = []
        cache_keys = [ref.cache_key(user_id) for ref in refs]
        if cache_keys:
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

        if len(contents) != len(refs):
            raise Unreachable(f"len(contents) != len(refs), {len(contents)} != {len(refs)}")

        return [
            MessageToFormat(ref=ref, content=content, reactions=reactions)
            for ref, content, reactions in zip(refs, contents, reactionss)
        ]

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
            fwd_header: models.MessageFwdHeader | None | Missing = MISSING,
            reply_to_content_id: int | None = None, drop_captions: bool = False, media_group_id: int | None = None,
            drop_author: bool = False, is_forward: bool = False, no_forwards: bool = False, pinned: bool | None = None,
            is_discussion: bool = False,
    ) -> list[Self]:
        content = await self.content.clone_forward(
            related_peer=to_peer,
            new_author=new_author,
            fwd_header=fwd_header,
            drop_captions=drop_captions,
            media_group_id=media_group_id,
            drop_author=drop_author,
            is_forward=is_forward,
            no_forwards=no_forwards,
            is_discussion=is_discussion,
        )

        if reply_to_content_id:
            replies = {
                ref.peer_id: ref
                for ref in await MessageRef.filter(
                    peer_id__in=[peer.id for peer in peers], content_id=reply_to_content_id,
                )
            }
        else:
            replies = {}

        messages = []
        for peer in peers:
            messages.append(await models.MessageRef.create(
                peer=peer,
                content=content,
                pinned=self.pinned if pinned is None else pinned,
                random_id=random_id if peer == to_peer else None,
                reply_to=replies.get(peer.id),
            ))

        return messages

    async def create_fwd_header(self, to_self: bool, discussion: bool = False) -> models.MessageFwdHeader:
        return await self.content.create_fwd_header(self, to_self, discussion)

    @classmethod
    async def create_for_peer(
            cls, peer: models.Peer, author: models.User, random_id: int | None = None,
            opposite: bool = True, unhide_dialog: bool = True, reply_to: MessageRef | None = None,
            **message_kwargs,
    ) -> dict[models.Peer, Self]:
        if random_id is not None and await cls.filter(peer=peer, random_id=random_id).exists():
            raise ErrorRpc(error_code=500, error_message="RANDOM_ID_DUPLICATE")

        content = await models.MessageContent.create_for_peer(
            related_peer=peer,
            author=author,
            **message_kwargs,
        )

        peers = [peer]
        if opposite and peer.type is not PeerType.CHANNEL:
            peers.extend(await peer.get_opposite())
        elif opposite and peer.type is PeerType.CHANNEL:
            peers = [await models.Peer.get_or_none(owner=None, channel=peer.channel, type=PeerType.CHANNEL)]

        messages: dict[models.Peer, MessageRef] = {}

        if reply_to is not None:
            replies = {
                ref.peer_id: ref
                for ref in await MessageRef.filter(
                    peer_id__in=[peer.id for peer in peers], content_id=reply_to.content_id,
                )
            }
        else:
            replies = {}

        for to_peer in peers:
            # TODO: probably create in bulk too?
            messages[to_peer] = await cls.create(
                peer=to_peer,
                content=content,
                random_id=random_id if to_peer == peer or to_peer.type is PeerType.CHANNEL else None,
                reply_to=replies.get(to_peer.id),
            )

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

    async def to_tl_reactions(self, user: models.User | int) -> MessageReactions:
        user_id = user.id if isinstance(user, models.User) else user

        user_reaction = await models.MessageReaction.get_or_none(
            user_id=user_id, message_id=self.content_id
        ).values_list("reaction_id", "custom_emoji_id")
        if user_reaction:
            user_reaction_id, user_custom_emoji_id = user_reaction
            cache_user_id = user_id
        elif self.content.author_id == user_id:
            user_reaction_id = user_custom_emoji_id = None
            cache_user_id = user_id
        else:
            user_reaction_id = user_custom_emoji_id = None
            cache_user_id = None

        if (cached := await Cache.obj.get(self.cache_key_reactions(cache_user_id))) is not None:
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
                if self.peer.type is PeerType.CHANNEL:
                    read_state = await models.ReadState.get_or_none(
                        peer__owner_id=user_id, peer__channel_id=self.peer.channel_id,
                    )
                else:
                    read_state = await models.ReadState.get_or_none(peer_id=self.peer_id)
                if read_state is not None:
                    last_read_id = read_state.last_reaction_id
                else:
                    last_read_id = 0
            else:
                last_read_id = 2 ** 63 - 1

            recent_reactions = []

            for recent in await models.MessageReaction.filter(
                    message_id=self.content_id,
            ).order_by("-date").limit(5).select_related("reaction"):
                recent_reactions.append(recent.to_tl_peer_reaction(user_id, last_read_id))

        result = MessageReactions(
            min=cache_user_id is None,
            can_see_list=can_see_list,
            results=results,
            recent_reactions=recent_reactions,
        )

        await Cache.obj.set(self.cache_key_reactions(cache_user_id), result)

        return result

    @classmethod
    async def to_tl_reactions_bulk(cls, messages: list[MessageRef], user_id: int) -> list[MessageReactions]:
        content_ids = [ref.content.id for ref in messages]

        user_reactions = {}
        for message_id, reaction_id, custom_emoji_id in await models.MessageReaction.filter(
            user_id=user_id, message_id__in=content_ids,
        ).values_list("message_id", "reaction_id", "custom_emoji_id"):
            user_reactions[message_id] = reaction_id, custom_emoji_id

        cache_keys = [
            ref.cache_key_reactions(
                user_id if ref.content_id in user_reactions or ref.content.author_id == user_id else None
            )
            for ref in messages
        ]
        cached_reactions = await Cache.obj.multi_get(cache_keys)

        not_cached_ids = [ref.content_id for ref, cached in zip(messages, cached_reactions) if cached is None]
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
            if cached is not None:
                results.append(cached)

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
                    if ref.peer.type is PeerType.CHANNEL:
                        read_state = await models.ReadState.get_or_none(
                            peer__owner_id=user_id, peer__channel_id=ref.peer.channel_id,
                        )
                    else:
                        read_state = await models.ReadState.get_or_none(peer_id=ref.peer_id)
                    if read_state is not None:
                        last_read_id = read_state.last_reaction_id
                    else:
                        last_read_id = 0
                else:
                    last_read_id = 2 ** 63 - 1

                recent_reactions = []

                for recent in await models.MessageReaction.filter(
                        message_id=ref.content_id,
                ).order_by("-date").limit(5).select_related("reaction"):
                    recent_reactions.append(recent.to_tl_peer_reaction(user_id, last_read_id))

            results.append(MessageReactions(
                min=ref.content_id not in user_reactions and ref.content.author_id != user_id,
                can_see_list=can_see_list,
                results=reaction_results,
                recent_reactions=recent_reactions,
            ))
            to_cache.append((cache_key, results[-1]))

        await Cache.obj.multi_set(to_cache)

        return results

    def cache_key_reactions(self, user_id: int | None) -> str:
        return f"message-reactions:{self.content_id}:{user_id or 0}:{self.content.reactions_version}"
