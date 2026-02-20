from __future__ import annotations

from typing import TypeVar, Self, Iterable

from tortoise import fields, Model
from tortoise.expressions import Q

from piltover.db import models
from piltover.db.enums import MessageType, PeerType
from piltover.db.models.utils import Missing, MISSING, NullableFKSetNull
from piltover.exceptions import ErrorRpc, Unreachable
from piltover.tl import MessageReplyHeader
from piltover.tl.base import Message as TLMessageBase

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

    async def to_tl(self, current_user: models.User, with_reactions: bool = False) -> TLMessageBase:
        return await self.content.to_tl(self, current_user, with_reactions)

    @classmethod
    async def to_tl_bulk(
            cls, messages: list[Self], user: models.User | int, with_reactions: bool = False,
    ) -> list[TLMessageBase]:
        contents = [message.content for message in messages]
        user_id = user if isinstance(user, int) else user.id
        return await models.MessageContent.to_tl_bulk(contents, messages, user_id, with_reactions)

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
                reply_to=replies.get(peer.id),
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
