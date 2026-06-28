from __future__ import annotations

from typing import Self, TypeVar

from tortoise import fields, Model
from tortoise.expressions import Q
from tortoise.queryset import QuerySet

from piltover.db import models
from piltover.db.enums import PeerType
from piltover.db.utils.awaitable_none_queryset import EmptyQuerySet
from piltover.exceptions import Unreachable
from piltover.tl.base import InputUser as TLInputUserBase, InputPeer as TLInputPeerBase, \
    InputChannel as TLInputChannelBase

DialogBaseT = TypeVar("DialogBaseT", bound="DialogBase")


class DialogBase(Model):
    id: int = fields.BigIntField(primary_key=True)
    pinned_index: int | None = fields.SmallIntField(null=True, default=None)
    owner: models.User = fields.ForeignKeyField("models.User")
    peer: models.Peer = fields.ForeignKeyField("models.Peer")

    owner_id: int
    peer_id: int

    class Meta:
        abstract = True

    @classmethod
    def top_message_query_bulk(
            cls, user_id: int, dialogs: list[Self], prefetch: bool = True
    ) -> QuerySet[models.MessageRef]:
        raise NotImplementedError

    @classmethod
    def get_from_input_peer(
            cls: type[DialogBaseT], user_id: int, input_peer: TLInputPeerBase | TLInputUserBase | TLInputChannelBase,
            error_message: str = "PEER_ID_INVALID",
    ) -> QuerySet[DialogBaseT]:
        peer_type, peer_target_id = models.Peer.type_and_id_from_input_raise(user_id, input_peer, error_message)
        if peer_type in (PeerType.SELF, PeerType.USER):
            peer_q = Q(peer__user_id=peer_target_id)
        elif peer_type is PeerType.CHAT:
            peer_q = Q(peer__chat_id=peer_target_id)
        elif peer_type is PeerType.CHANNEL:
            peer_q = Q(peer__channel_id=peer_target_id)
        else:
            raise Unreachable

        return cls.filter(peer_q, owner_id=user_id)

    @classmethod
    def get_from_input_peer_many(
            cls: type[DialogBaseT], user_id: int,
            input_peers: list[TLInputPeerBase | TLInputUserBase | TLInputChannelBase],
    ) -> QuerySet[DialogBaseT]:
        peer_user_ids: set[int] = set()
        peer_chat_ids: set[int] = set()
        peer_channel_ids: set[int] = set()

        for input_peer in input_peers:
            peer_info = models.Peer.type_and_id_from_input(user_id, input_peer)
            if peer_info is None:
                continue

            peer_type, peer_target_id = peer_info
            if peer_type in (PeerType.SELF, PeerType.USER):
                peer_user_ids.add(peer_target_id)
            elif peer_type is PeerType.CHAT:
                peer_chat_ids.add(peer_target_id)
            elif peer_type is PeerType.CHANNEL:
                peer_channel_ids.add(peer_target_id)
            else:
                raise Unreachable

        if peer_user_ids or peer_chat_ids or peer_channel_ids:
            peers_q = Q(
                peer__user_id__in=peer_user_ids,
                peer__chat_id__in=peer_chat_ids,
                peer__channel_id__in=peer_channel_ids,
                join_type=Q.OR
            )
            return cls.filter(peers_q, owner_id=user_id, visible=True)

        return EmptyQuerySet(cls)
