from __future__ import annotations

from typing import TypeVar, Self, Iterable

from tortoise import fields, Model
from tortoise.expressions import Q

from piltover.cache import Cache
from piltover.db import models
from piltover.db.enums import MessageType, PeerType, READABLE_FILE_TYPES
from piltover.db.models.utils import Missing, MISSING, NullableFKSetNull
from piltover.exceptions import ErrorRpc, Unreachable
from piltover.tl import MessageReplyHeader, MessageReactions, PeerUser
from piltover.tl.base import Message as TLMessageBase
from piltover.tl.base.internal import MessageToFormatRef
from piltover.tl.to_format import MessageToFormat
from piltover.tl.types.internal import MessageToFormatContent

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
            self, out: bool, reactions: MessageReactions | None, mentioned: bool, media_unread: bool,
    ) -> MessageToFormatRef:
        return MessageToFormatRef(
            id=self.id,
            pinned=self.pinned,
            peer_id=self.peer.to_tl(),
            out=out,
            reply_to=self.make_reply_to_header(),
            reactions=reactions if reactions is not None and not reactions.min else None,
            mentioned=mentioned,
            media_unread=media_unread,
            from_scheduled=self.from_scheduled or self.content.scheduled_date,
        )

    async def to_tl_ref(
            self, user: models.User, to_format: MessageToFormat, with_reactions: bool,
            reactions: MessageReactions | None,
    ) -> MessageToFormatRef:
        # TODO: cache it and just delete from cache when user reads mention?
        # cache_key = ref.cache_key(current_user.id)
        # if (cached := await Cache.obj.get(cache_key)) is not None:
        #     if with_reactions:
        #         reactions_before = to_format.ref.reactions
        #         to_format.reactions = reactions
        #         if reactions_before != to_format.ref.reactions:
        #             await Cache.obj.set(cache_key, cached)
        #     return cached

        mention_read = await models.MessageMention.filter(
            user=user, message=self
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
            reactions=reactions,
            mentioned=mentioned,
            media_unread=media_unread if media_unread else not mention_read,
        )

        # await Cache.obj.set(cache_key, message)
        return message

    async def to_tl(self, user: models.User, with_reactions: bool = False) -> TLMessageBase:
        result = MessageToFormat(
            ref=MessageToFormatRef(
                id=0,
                peer_id=PeerUser(user_id=0),
            ),
            content=MessageToFormatContent(
                date=0,
                message="",
            ),
        )

        reactions = None
        if with_reactions and self.content.type is MessageType.REGULAR:
            reactions = await self.content.to_tl_reactions(user)

        result.ref = await self.to_tl_ref(user, result, with_reactions, reactions)
        result.content = await self.content.to_tl_content(result, with_reactions, reactions)

        return result

    @classmethod
    async def to_tl_ref_bulk(
            cls, refs: list[models.MessageRef], user_id: int, to_formats: list[MessageToFormat],
            with_reactions: bool, reactionss: list[MessageReactions | None],
    ) -> list[TLMessageBase]:
        cached = []
        cache_keys = [ref.cache_key(user_id) for ref in refs]
        if cache_keys:
            cached = await Cache.obj.multi_get(cache_keys)

        message_content_ids = {
            ref.content.id
            for ref, cached_ref in zip(refs, cached)
            if cached_ref is not None and not ref.content.is_service()
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
        for ref, cached_ref, reactions, to_format in zip(refs, cached, reactionss, to_formats):
            msg_media_unread = ref.id not in media_read and not mentioned.get(ref.content.id, True)

            if cached_ref is not None:
                to_format.ref = cached_ref
                result.append(cached_ref)
                need_recache = False

                if result[-1].media_unread != msg_media_unread:
                    result[-1].media_unread = msg_media_unread
                    need_recache = True

                if with_reactions:
                    reactions_before = to_format.ref.reactions
                    to_format.reactions = reactions
                    need_recache = need_recache or reactions_before != to_format.ref.reactions

                if need_recache:
                    to_cache.append((ref.cache_key(user_id), result[-1]))

                continue

            result.append(ref._to_tl_ref(
                out=user_id == ref.content.author_id,
                reactions=reactions,
                mentioned=ref.content_id in mentioned,
                media_unread=msg_media_unread,
            ))

            to_cache.append((ref.cache_key(user_id), result[-1]))

        if to_cache:
            await Cache.obj.multi_set(to_cache)

        return result

    @classmethod
    async def to_tl_bulk(
            cls, messages: list[MessageRef], user: models.User | int, with_reactions: bool = False,
    ) -> list[TLMessageBase]:
        user_id = user.id if isinstance(user, models.User) else user

        result = [
            MessageToFormat(
                ref=MessageToFormatRef(
                    id=0,
                    peer_id=PeerUser(user_id=0),
                ),
                content=MessageToFormatContent(
                    date=0,
                    message="",
                ),
            )
            for _ in messages
        ]

        raw_contents = [ref.content for ref in messages]

        reactions = [None for _ in messages]
        if with_reactions:
            for idx, content in enumerate(raw_contents):
                reactions[idx] = await content.to_tl_reactions(user_id)

        refs = await MessageRef.to_tl_ref_bulk(messages, user_id, result, with_reactions, reactions)
        contents = await models.MessageContent.to_tl_content_bulk(raw_contents, result, with_reactions, reactions)

        if len(refs) != len(result):
            raise Unreachable(f"len(refs) != len(result), {len(refs)} != {len(result)}")
        if len(contents) != len(result):
            raise Unreachable(f"len(contents) != len(result), {len(contents)} != {len(result)}")

        for to_format, ref, content in zip(result, refs, contents):
            to_format.ref = ref
            to_format.content = content

        return result

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
