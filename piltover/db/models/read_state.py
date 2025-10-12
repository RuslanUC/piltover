from __future__ import annotations

from tortoise import fields, Model
from tortoise.expressions import Q

from piltover.db import models
from piltover.db.enums import PeerType


class ReadState(Model):
    id: int = fields.BigIntField(pk=True)
    last_message_id: int = fields.BigIntField(default=0)
    last_reaction_id: int = fields.BigIntField(default=0)
    last_mention_id: int = fields.BigIntField(default=0)
    peer: models.Peer = fields.ForeignKeyField("models.Peer", on_delete=fields.CASCADE, unique=True)

    @classmethod
    async def for_peer(cls, peer: models.Peer) -> ReadState:
        read_state, _ = await models.ReadState.get_or_create(peer=peer)
        return read_state

    @classmethod
    async def get_in_out_ids_and_unread(
            cls, peer: models.Peer, no_reactions: bool = False, no_mentions: bool = False,
    ) -> tuple[int, int, int, int, int]:
        in_read_state = await cls.for_peer(peer=peer)
        unread_count = await models.Message.filter(peer=peer, id__gt=in_read_state.last_message_id).count()
        if no_reactions:
            unread_reactions_count = 0
        else:
            unread_reactions_count = await models.MessageReaction.filter(
                Q(message__author__id=peer.owner_id, id__gt=in_read_state.last_reaction_id)
                & (
                    Q(message__peer__owner__id=peer.owner_id, message__peer__channel__id=peer.channel_id)
                    if peer.type is PeerType.CHANNEL
                    else Q(message__peer=peer)
                )
                & Q(user__id__not=peer.owner_id),
            ).count()

        out_read_max_id = 0
        if peer.type is PeerType.SELF:
            out_read_max_id = in_read_state.last_message_id
        elif peer.type is PeerType.USER:
            out_read_max_id = await models.ReadState.filter(
                peer__owner__id=peer.user_id, peer__user__id=peer.owner_id
            ).first().values_list("last_message_id", flat=True) or 0
        elif peer.type is PeerType.CHAT:
            out_read_state = await models.ReadState.filter(
                peer__chat__id=peer.chat_id, peer__id__not=peer.id
            ).order_by("-last_message_id").first()
            if out_read_state:
                out_read_max_id = await models.Message.filter(
                    peer=peer, id__lte=out_read_state.last_message_id
                ).order_by("-id").first().values_list("id", flat=True)
                out_read_max_id = out_read_max_id or 0
        elif peer.type is PeerType.CHANNEL:
            out_read_max_id = 0
            # TODO: if supergroup, do same as in case with PeerType.CHAT
            # out_read_state = await models.ReadState.filter(
            #     peer__channel__id=self.peer.channel_id, peer__id__not=self.peer.id
            # ).order_by("-last_message_id").first()
            # if out_read_state:
            #     out_read_max_id = await models.Message.filter(
            #         peer=self.peer, id__lte=out_read_state.last_message_id
            #     ).order_by("-id").first().values_list("id", flat=True)
            #     out_read_max_id = out_read_max_id or 0

        if no_mentions:
            unread_mentions = 0
        else:
            unread_mentions = await models.MessageMention.filter(
                peer=peer, id__gt=in_read_state.last_mention_id,
            ).count()

        return (
            in_read_state.last_message_id,
            out_read_max_id or 0,
            unread_count,
            unread_reactions_count,
            unread_mentions,
        )

