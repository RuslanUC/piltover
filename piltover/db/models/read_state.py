from __future__ import annotations

from pypika_tortoise import Dialects, Parameter
from tortoise import fields, Model, Tortoise
from tortoise.functions import Count
from tortoise.transactions import in_transaction

from piltover.db import models
from piltover.db.enums import PeerType
from piltover.exceptions import Unreachable

_UNREAD_COUNTS_SQL = """
SELECT
    state.peer_id peer, COUNT(mref.id) count
FROM readstate state
    JOIN messageref mref on state.peer_id = mref.peer_id and mref.id > state.last_message_id
WHERE state.owner_id = {user_id_param} AND state.peer_id {peer_condition}
GROUP BY state.peer_id
;
"""


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
        # TODO: add index on peer-last_message_id?

    @classmethod
    async def for_peers_bulk(cls, user_id: int, peers: list[models.Peer]) -> list[ReadState]:
        peer_ids = {peer.id for peer in peers}
        async with in_transaction():
            read_states = {ex.peer_id: ex for ex in await cls.filter(owner_id=user_id, peer_id__in=peer_ids)}
            to_create = [ReadState(owner_id=user_id, peer=peer) for peer in peers if peer.id not in read_states]
            if to_create:
                await ReadState.bulk_create(to_create)

        created = peer_ids - read_states.keys()
        if created:
            for state in await cls.filter(owner_id=user_id, peer_id__in=created):
                read_states[state.peer_id] = state

        return [read_states[peer.id] for peer in peers]

    @classmethod
    async def get_in_out_ids_and_unread_bulk(
            cls, user_id: int, peers: list[models.Peer], no_reactions: bool = False, no_mentions: bool = False,
    ) -> list[tuple[int, int, int, int, int]]:
        if not peers:
            return []

        in_read_states = await cls.for_peers_bulk(user_id, peers)

        fetch_unreads_for = []
        for peer, read_state in zip(peers, in_read_states):
            if (peer.last_message_id or 0) > read_state.last_message_id:
                fetch_unreads_for.append(peer.id)

        unread_by_peer = {}
        if fetch_unreads_for:
            conn = Tortoise.get_connection("default")
            dialect = Dialects(conn.capabilities.dialect)
            placeholder_factory = Parameter.IDX_PLACEHOLDERS[dialect]
            placeholders = [placeholder_factory(i + 1) for i in range(len(peers) + 1)]

            if len(peers) == 1:
                where_condition = f"= {placeholders[1]}"
            else:
                where_condition = f"IN ({','.join(placeholders[1:])})"

            sql = _UNREAD_COUNTS_SQL.format(user_id_param=placeholders[0], peer_condition=where_condition)
            params = [user_id]
            for peer in peers:
                params.append(peer.id)

            _, results = await conn.execute_query(sql, params)
            for res in results:
                unread_by_peer[res["peer"]] = res["count"]

        unread_reactions_by_peer = {}
        if not no_reactions:
            unread_reactions_counts = await models.MessageContent.filter(
                author_id=user_id,
                author_reactions_unread=True,
                messagerefs__peer_id__in=[peer.id for peer in peers],
            ).group_by(
                "messagerefs__peer_id",
            ).annotate(
                count=Count("id"),
            ).values_list("messagerefs__peer_id", "count")
            unread_reactions_by_peer: dict[int, int] = dict(unread_reactions_counts)

        unread_mentions_by_chat = {}
        if not no_mentions:
            unread_target_ids = set()
            for peer in peers:
                if peer.id not in unread_by_peer:
                    # If no new messages - there can't be new mentions
                    continue
                if peer.type is PeerType.CHANNEL:
                    unread_target_ids.add(models.Channel.make_id_from(peer.channel_id))
                elif peer.type is PeerType.CHAT:
                    unread_target_ids.add(models.Chat.make_id_from(peer.chat_id))

            if unread_target_ids:
                mentions = await models.MessageMention.filter(
                    user_id=user_id, unread_target_id__in=unread_target_ids,
                ).group_by(
                    "unread_target_id",
                ).annotate(
                    count=Count("id"),
                ).values_list(
                    "unread_target_id", "count",
                )

                for unread_target_id, count in mentions:
                    unread_mentions_by_chat[unread_target_id] = count

        result = []
        for peer, in_read_state in zip(peers, in_read_states):
            unread_target_id = None
            if peer.type is PeerType.CHAT:
                unread_target_id = models.Chat.make_id_from(peer.chat_id)
            elif peer.type is PeerType.CHANNEL:
                unread_target_id = models.Channel.make_id_from(peer.channel_id)
            result.append((
                in_read_state.last_message_id,
                peer.out_max_read_id,
                unread_by_peer.get(peer.id, 0),
                unread_reactions_by_peer.get(peer.id, 0),
                unread_mentions_by_chat.get(unread_target_id, 0),
            ))

        return result

    @classmethod
    async def get_in_out_ids_and_unread(
            cls, user_id: int, peer: models.Peer, no_reactions: bool = False, no_mentions: bool = False,
    ) -> tuple[int, int, int, int, int]:
        in_read_state, _ = await models.ReadState.get_or_create(owner_id=user_id, peer=peer)
        unread_count = await models.MessageRef.filter(peer=peer, id__gt=in_read_state.last_message_id).count()
        if no_reactions:
            unread_reactions_count = 0
        else:
            unread_reactions_count = await models.MessageContent.filter(
                messagerefs__peer=peer,
                author_id=user_id,
                author_reactions_unread=True,
            ).count()

        if not unread_count or no_mentions or peer.type not in (PeerType.CHAT, PeerType.CHANNEL):
            unread_mentions = 0
        else:
            if peer.type is PeerType.CHAT:
                unread_target_id = models.Chat.make_id_from(peer.chat_id)
            elif peer.type is PeerType.CHANNEL:
                unread_target_id = models.Channel.make_id_from(peer.channel_id)
            else:
                raise Unreachable
            unread_mentions = await models.MessageMention.filter(
                user_id=user_id, unread_target_id=unread_target_id,
            ).count()

        return (
            in_read_state.last_message_id,
            peer.out_max_read_id,
            unread_count,
            unread_reactions_count,
            unread_mentions,
        )
