from __future__ import annotations

from tortoise import fields, Model
from tortoise.expressions import Q

from piltover.db import models
from piltover.db.enums import PeerType
from piltover.exceptions import Unreachable


class ReadState(Model):
    id: int = fields.BigIntField(pk=True)
    last_message_id: int = fields.BigIntField(default=0)
    last_reaction_id: int = fields.BigIntField(default=0)
    peer: models.Peer = fields.OneToOneField("models.Peer")

    peer_id: int

    @classmethod
    async def for_peer(cls, peer: models.Peer) -> ReadState:
        read_state, _ = await models.ReadState.get_or_create(peer=peer)
        return read_state

    @classmethod
    async def for_peer_chat(cls, user_id: int, chat_id: int) -> ReadState:
        read_state, _ = await models.ReadState.get_or_create(peer__owner_id=user_id, peer__chat_id=chat_id)
        return read_state

    @classmethod
    async def get_in_out_ids_and_unread(
            cls, peer: models.Peer, no_reactions: bool = False, no_mentions: bool = False, no_out_id: bool = False
    ) -> tuple[int, int, int, int, int]:
        in_read_state = await cls.for_peer(peer=peer)
        unread_count = await models.MessageRef.filter(
            peer.q_this_or_channel(), id__gt=in_read_state.last_message_id, content__author_id__not=peer.owner_id,
        ).count()
        if no_reactions:
            unread_reactions_count = 0
        else:
            unread_reactions_count = await models.MessageReaction.filter(
                Q(message__author_id=peer.owner_id, id__gt=in_read_state.last_reaction_id)
                & (
                    Q(
                        message__messagerefs__peer__owner_id=peer.owner_id,
                        message__messagerefs__peer__channel_id=peer.channel_id
                    )
                    if peer.type is PeerType.CHANNEL
                    else Q(message__messagerefs__peer=peer)
                )
                & Q(user_id__not=peer.owner_id),
            ).count()

        out_read_max_id = 0
        if not no_out_id:
            if peer.type is PeerType.SELF:
                out_read_max_id = in_read_state.last_message_id
            elif peer.type is PeerType.USER:
                out_read_max_id = await models.ReadState.filter(
                    peer__owner_id=peer.user_id, peer__user_id=peer.owner_id
                ).first().values_list("last_message_id", flat=True) or 0
            elif peer.type is PeerType.CHAT:
                # TODO: probably can be done in one query?
                out_read_state = await models.ReadState.filter(
                    peer__chat_id=peer.chat_id, peer_id__not=peer.id
                ).order_by("-last_message_id").first()
                if out_read_state:
                    out_read_max_id = await models.MessageRef.filter(
                        peer=peer, id__lte=out_read_state.last_message_id
                    ).order_by("-id").first().values_list("id", flat=True)
                    out_read_max_id = out_read_max_id or 0
            elif peer.type is PeerType.CHANNEL:
                out_read_max_id = 0
                # TODO: if supergroup, do same as in case with PeerType.CHAT
                # out_read_state = await models.ReadState.filter(
                #     peer__channel_id=self.peer.channel_id, peer_id__not=self.peer.id
                # ).order_by("-last_message_id").first()
                # if out_read_state:
                #     out_read_max_id = await models.Message.filter(
                #         peer=self.peer, id__lte=out_read_state.last_message_id
                #     ).order_by("-id").first().values_list("id", flat=True)
                #     out_read_max_id = out_read_max_id or 0

        if no_mentions or peer.type not in (PeerType.CHAT, PeerType.CHANNEL):
            unread_mentions = 0
        else:
            if peer.type is PeerType.CHAT:
                unread_mentions_query = models.MessageMention.filter(chat_id=peer.chat_id)
            elif peer.type is PeerType.CHANNEL:
                unread_mentions_query = models.MessageMention.filter(channel_id=peer.channel_id)
            else:
                raise Unreachable
            unread_mentions = await unread_mentions_query.filter(read=False, user_id=peer.owner_id).count()

        return (
            in_read_state.last_message_id,
            out_read_max_id or 0,
            unread_count,
            unread_reactions_count,
            unread_mentions,
        )
