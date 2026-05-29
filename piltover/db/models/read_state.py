from __future__ import annotations

from tortoise import fields, Model
from tortoise.expressions import Q
from tortoise.functions import Count, Max
from tortoise.transactions import in_transaction

from piltover.db import models
from piltover.db.enums import PeerType
from piltover.exceptions import Unreachable


class ReadState(Model):
    id: int = fields.BigIntField(primary_key=True)
    last_message_id: int = fields.BigIntField(default=0)
    owner: models.User = fields.ForeignKeyField("models.User")
    peer: models.Peer = fields.ForeignKeyField("models.Peer")

    owner_id: int
    peer_id: int

    class Meta:
        unique_together = (
            ("owner_id", "peer_id"),
        )

    @classmethod
    async def for_peer_bulk(cls, user_id: int, peers: list[models.Peer]) -> list[ReadState]:
        peer_ids = [peer.id for peer in peers]
        async with in_transaction():
            existing = await cls.filter(owner_id=user_id, peer_id__in=peer_ids).values_list("peer_id", flat=True)
            existing = set(existing)
            to_create = [ReadState(owner_id=user_id, peer=peer) for peer in peers if peer.id not in existing]
            if to_create:
                await ReadState.bulk_create(to_create)

        read_states = {state.peer_id: state for state in await cls.filter(owner_id=user_id, peer_id__in=peer_ids)}
        return [read_states[peer.id] for peer in peers]

    @classmethod
    async def get_in_out_ids_and_unread_bulk(
            cls, user_id: int, peers: list[models.Peer], no_reactions: bool = False, no_mentions: bool = False,
            no_out_id: bool = False,
    ) -> list[tuple[int, int, int, int, int]]:
        if not peers:
            return []

        in_read_states = await cls.for_peer_bulk(user_id, peers)

        unreads_queries = [
            Q(peer=peer, id__gt=in_read_state.last_message_id)
            for peer, in_read_state in zip(peers, in_read_states)
        ]
        unread_counts = await models.MessageRef.filter(
            Q(*unreads_queries, join_type=Q.OR), content__author_id__not=user_id,
        ).group_by("peer_id").annotate(count=Count("id")).values_list("peer_id", "count")
        unread_by_peer: dict[int, int] = dict(unread_counts)

        unread_reactions_by_peer = {}
        if not no_reactions:
            unread_reactions_counts = await models.MessageReaction.filter(
                user_id__not=user_id,
                message__author_id=user_id,
                message__author_reactions_unread=True,
                message__messagerefs__peer_id__in=[peer.id for peer in peers],
            ).group_by(
                "message__messagerefs__peer_id",
            ).annotate(
                count=Count("message_id"),
            ).values_list("message__messagerefs__peer_id", "count")
            unread_reactions_by_peer: dict[int, int] = dict(unread_reactions_counts)

        out_read_max_ids = {}
        if not no_out_id:
            user_ids = []
            chat_ids = []
            channel_ids = []

            for peer, in_read_state in zip(peers, in_read_states):
                if peer.type is PeerType.SELF:
                    out_read_max_ids[(peer.type, peer.target_id_raw())] = in_read_state.last_message_id
                elif peer.type is PeerType.USER:
                    user_ids.append(peer.user_id)
                elif peer.type is PeerType.CHAT:
                    chat_ids.append(peer.chat_id)
                elif peer.type is PeerType.CHANNEL:
                    channel_ids.append(peer.channel_id)
                else:
                    raise Unreachable

            if user_ids:
                out_user_read_states = await models.ReadState.filter(
                    owner_id__in=user_ids, peer__user_id=user_id,
                ).group_by(
                    "owner_id",
                ).annotate(
                    last_id=Max("last_message_id"),
                ).values_list(
                    "owner_id", "last_id",
                )
                for other_user_id, last_id in out_user_read_states:
                    out_read_max_ids[(PeerType.USER, other_user_id)] = last_id

            if chat_ids:
                out_last_ids = await models.ReadState.filter(
                    peer__chat_id__in=chat_ids, owner_id__not=user_id,
                ).group_by(
                    "peer__chat_id",
                ).annotate(
                    last_id=Max("last_message_id"),
                ).values_list(
                    "last_id", "peer__chat_id",
                )
                id_to_chat = dict(out_last_ids)
                content_to_ref = await models.MessageRef.filter(id__in=id_to_chat).values_list("content_id", "id")
                content_to_ref = dict(content_to_ref)
                query_parts = []
                for content_id, ref_id in content_to_ref.items():
                    chat_id = id_to_chat[ref_id]
                    query_parts.append(Q(peer__chat_id=chat_id, content_id__lte=content_id))
                if query_parts:
                    our_ids = await models.MessageRef.filter(
                        Q(*query_parts, join_type=Q.OR), content__author_id=user_id, peer__owner_id=user_id,
                    ).values_list("content_id", "id")
                else:
                    our_ids = []

                for content_id, ref_id in our_ids:
                    chat_id = id_to_chat[content_to_ref[content_id]]
                    out_read_max_ids[(PeerType.CHAT, chat_id)] = ref_id

            if channel_ids:
                out_last_ids = await models.ReadState.filter(
                    peer__channel_id__in=channel_ids, owner_id__not=user_id,
                ).group_by(
                    "peer_id",
                ).annotate(
                    last_id=Max("last_message_id"),
                ).values_list(
                    "last_id", "peer_id",
                )
                query_parts = []
                for ref_id, peer_id in out_last_ids:
                    query_parts.append(Q(peer_id=peer_id, id__lte=ref_id))
                if query_parts:
                    our_ids = await models.MessageRef.filter(
                        Q(*query_parts, join_type=Q.OR), content__author_id=user_id,
                    ).values_list("peer__channel_id", "id")
                else:
                    our_ids = []

                for channel_id, ref_id in our_ids:
                    out_read_max_ids[(PeerType.CHANNEL, channel_id)] = ref_id

        unread_mentions_by_chat = {}
        if not no_mentions:
            mentions_query = models.MessageMention.filter(read=False, user_id=user_id)
            chat_ids = set()
            channel_ids = set()
            for peer in peers:
                if peer.type is PeerType.CHANNEL:
                    channel_ids.add(peer.channel_id)
                elif peer.type is PeerType.CHAT:
                    chat_ids.add(peer.chat_id)

            query_parts = Q()
            if chat_ids:
                query_parts |= Q(chat_id__in=chat_ids)
            if channel_ids:
                query_parts |= Q(chat_id__in=channel_ids)

            if query_parts:
                mentions = await mentions_query.filter(
                    query_parts,
                ).group_by(
                    "chat_id", "channel_id",
                ).annotate(
                    count=Count("id"),
                ).values_list(
                    "chat_id", "channel_id", "count",
                )

                for chat_id, channel_id, count in mentions:
                    unread_mentions_by_chat[(chat_id, channel_id)] = count

        result = []
        for peer, in_read_state in zip(peers, in_read_states):
            result.append((
                in_read_state.last_message_id,
                out_read_max_ids.get((peer.type, peer.target_id_raw()), 0),
                unread_by_peer.get(peer.id, 0),
                unread_reactions_by_peer.get(peer.id, 0),
                unread_mentions_by_chat.get((peer.chat_id, peer.channel_id), 0),
            ))

        return result

    @classmethod
    async def get_in_out_ids_and_unread(
            cls, user_id: int, peer: models.Peer, no_reactions: bool = False, no_mentions: bool = False,
            no_out_id: bool = False,
    ) -> tuple[int, int, int, int, int]:
        in_read_state, _ = await models.ReadState.get_or_create(owner_id=user_id, peer=peer)
        unread_count = await models.MessageRef.filter(
            peer=peer, id__gt=in_read_state.last_message_id, content__author_id__not=user_id,
        ).count()
        if no_reactions:
            unread_reactions_count = 0
        else:
            unread_reactions_count = await models.MessageContent.filter(
                messagerefs__peer=peer,
                messagereactions__user_id__not=user_id,
                author_id=user_id,
                author_reactions_unread=True,
            ).count()

        out_read_max_id = 0
        if not no_out_id:
            if peer.type is PeerType.SELF:
                out_read_max_id = in_read_state.last_message_id
            elif peer.type is PeerType.USER:
                out_read_max_id = await models.ReadState.filter(
                    peer__owner_id=peer.user_id, peer__user_id=user_id
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
                # TODO: probably can be done in one query?
                out_read_state = await models.ReadState.filter(
                    peer=peer, owner_id__not=user_id,
                ).order_by("-last_message_id").first()
                if out_read_state:
                    out_read_max_id = await models.MessageRef.filter(
                        peer=peer, content__author_id=user_id, id__lte=out_read_state.last_message_id
                    ).order_by("-id").first().values_list("id", flat=True)
                    out_read_max_id = out_read_max_id or 0

        if no_mentions or peer.type not in (PeerType.CHAT, PeerType.CHANNEL):
            unread_mentions = 0
        else:
            if peer.type is PeerType.CHAT:
                unread_mentions_query = models.MessageMention.filter(chat_id=peer.chat_id)
            elif peer.type is PeerType.CHANNEL:
                unread_mentions_query = models.MessageMention.filter(channel_id=peer.channel_id)
            else:
                raise Unreachable
            unread_mentions = await unread_mentions_query.filter(read=False, user_id=user_id).count()

        return (
            in_read_state.last_message_id,
            out_read_max_id or 0,
            unread_count,
            unread_reactions_count,
            unread_mentions,
        )
