from __future__ import annotations

from tortoise import fields, Model
from tortoise.expressions import Q
from tortoise.transactions import in_transaction

from piltover.db import models
from piltover.db.enums import PeerType
from piltover.tl import DialogFilter, InputPeerSelf, InputPeerUser, InputPeerChat, InputPeerChannel


class DialogFolder(Model):
    id: int = fields.BigIntField(pk=True)
    id_for_user: int = fields.SmallIntField()
    name: str = fields.CharField(max_length=16)
    owner: models.User = fields.ForeignKeyField("models.User")
    position: int = fields.SmallIntField(default=0)
    contacts: bool = fields.BooleanField(default=False)
    non_contacts: bool = fields.BooleanField(default=False)
    groups: bool = fields.BooleanField(default=False)
    broadcasts: bool = fields.BooleanField(default=False)
    bots: bool = fields.BooleanField(default=False)
    exclude_muted: bool = fields.BooleanField(default=False)
    exclude_read: bool = fields.BooleanField(default=False)
    exclude_archived: bool = fields.BooleanField(default=False)

    pinned_peers: fields.ManyToManyRelation[models.Peer] = fields.ManyToManyField("models.Peer", related_name="pinned_peers")
    include_peers: fields.ManyToManyRelation[models.Peer] = fields.ManyToManyField("models.Peer", related_name="include_peers")
    exclude_peers: fields.ManyToManyRelation[models.Peer] = fields.ManyToManyField("models.Peer", related_name="exclude_peers")

    owner_id: int

    async def to_tl(self) -> DialogFilter:
        # TODO: select only type, id and access_hash
        pinned_peers = await self.pinned_peers.all()
        include_peers = await self.include_peers.all()
        exclude_peers = await self.exclude_peers.all()

        return DialogFilter(
            id=self.id,
            title=self.name,
            contacts=self.contacts,
            non_contacts=self.non_contacts,
            groups=self.groups,
            broadcasts=self.broadcasts,
            bots=self.bots,
            exclude_muted=self.exclude_muted,
            exclude_read=self.exclude_read,
            exclude_archived=self.exclude_archived,
            pinned_peers=[peer.to_input_peer() for peer in pinned_peers],
            include_peers=[peer.to_input_peer() for peer in include_peers],
            exclude_peers=[peer.to_input_peer() for peer in exclude_peers],
        )

    def get_difference(self, tl_filter: DialogFilter) -> list[str]:
        updated_fields = []
        for slot in tl_filter.__slots__:
            if not hasattr(self, slot):
                continue
            if getattr(self, slot) != getattr(tl_filter, slot):
                updated_fields.append(slot)

        if self.name != tl_filter.title:
            updated_fields.append("name")

        return updated_fields

    async def _fetch_peers(
            self, input_peers: list[InputPeerSelf | InputPeerUser | InputPeerChat | InputPeerChannel]
    ) -> list[models.Peer]:
        if not input_peers:
            return []

        query = Q()
        for input_peer in input_peers:
            if isinstance(input_peer, InputPeerSelf) \
                    or (isinstance(input_peer, InputPeerUser) and input_peer.user_id == self.owner_id):
                query |= Q(owner__id=self.owner_id, type=PeerType.SELF)
            elif isinstance(input_peer, InputPeerUser):
                query |= Q(
                    owner__id=self.owner_id, user__id=input_peer.user_id, access_hash=input_peer.access_hash,
                    type=PeerType.USER,
                )
            elif isinstance(input_peer, InputPeerChat):
                query |= Q(owner__id=self.owner_id, chat__id=input_peer.chat_id, type=PeerType.CHAT)
            elif isinstance(input_peer, InputPeerChannel):
                query |= Q(
                    owner__id=self.owner_id, channel__id=input_peer.channel_id, access_hash=input_peer.access_hash,
                    type=PeerType.CHANNEL,
                )

        return await models.Peer.filter(query)

    @staticmethod
    def _diff_peers(
            old_peers: dict[int, models.Peer], new_peers: dict[int, models.Peer],
    ) -> tuple[list[models.Peer], list[models.Peer]]:
        to_delete_ids = old_peers.keys() - new_peers.keys()
        to_add_ids = new_peers.keys() - old_peers.keys()

        to_delete = [old_peers[peer_id] for peer_id in to_delete_ids]
        to_add = [new_peers[peer_id] for peer_id in to_add_ids]

        return to_delete, to_add

    async def fill_from_tl(self, tl_filter: DialogFilter) -> None:
        self.name = tl_filter.title
        self.contacts = tl_filter.contacts
        self.non_contacts = tl_filter.non_contacts
        self.groups = tl_filter.groups
        self.broadcasts = tl_filter.broadcasts
        self.bots = tl_filter.bots
        self.exclude_muted = tl_filter.exclude_muted
        self.exclude_read = tl_filter.exclude_read
        self.exclude_archived = tl_filter.exclude_archived

        async with in_transaction():
            peer: models.Peer
            pinned_peers = {peer.id: peer async for peer in self.pinned_peers.all()}
            include_peers = {peer.id: peer async for peer in self.include_peers.all()}
            exclude_peers = {peer.id: peer async for peer in self.exclude_peers.all()}

            new_pinned_peers = {peer.id: peer for peer in await self._fetch_peers(tl_filter.pinned_peers)}
            new_include_peers = {peer.id: peer for peer in await self._fetch_peers(tl_filter.include_peers)}
            new_exclude_peers = {peer.id: peer for peer in await self._fetch_peers(tl_filter.exclude_peers)}

            delete_pinned, add_pinned = self._diff_peers(pinned_peers, new_pinned_peers)
            delete_include, add_include = self._diff_peers(include_peers, new_include_peers)
            delete_exclude, add_exclude = self._diff_peers(exclude_peers, new_exclude_peers)

            await self.pinned_peers.remove(*delete_pinned)
            await self.include_peers.remove(*delete_include)
            await self.exclude_peers.remove(*delete_exclude)

            await self.pinned_peers.add(*add_pinned)
            await self.include_peers.add(*add_include)
            await self.exclude_peers.add(*add_exclude)
