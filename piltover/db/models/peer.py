from __future__ import annotations

from os import urandom

from tortoise import fields

from piltover.db import models
from piltover.db.enums import PeerType
from piltover.db.models._utils import Model
from piltover.exceptions import ErrorRpc
from piltover.tl import PeerUser, InputPeerUser, InputPeerSelf, InputUserSelf, InputUser, PeerChat, InputPeerChat


def gen_access_hash() -> int:
    return int.from_bytes(urandom(8)) >> 2


InputPeers = InputPeerSelf | InputPeerUser | InputUserSelf | InputUser | InputPeerChat


class Peer(Model):
    id: int = fields.BigIntField(pk=True)
    owner: models.User = fields.ForeignKeyField("models.User", related_name="owner", null=True)
    type: PeerType = fields.IntEnumField(PeerType)
    access_hash: int = fields.BigIntField(default=gen_access_hash)
    blocked: bool = fields.BooleanField(default=False)

    user: models.User | None = fields.ForeignKeyField("models.User", related_name="user", null=True, default=None)
    chat: models.Chat | None = fields.ForeignKeyField("models.Chat", null=True, default=None)

    class Meta:
        unique_together = (
            ("owner", "type", "user"),
        )

    owner_id: int
    user_id: int
    chat_id: int

    def peer_user(self, user: models.User | None = None) -> models.User | None:
        return (user or self.owner) if self.type is PeerType.SELF else self.user

    @classmethod
    async def from_user_id(cls, user: models.User, user_id: int) -> Peer | None:
        if user.id == user_id:
            return await Peer.get_or_none(owner=user, type=PeerType.SELF)
        return await Peer.get_or_none(owner=user, user__id=user_id, type=PeerType.USER).select_related("user")

    @classmethod
    async def from_chat_id(cls, user: models.User, chat_id: int) -> Peer | None:
        return await Peer.get_or_none(owner=user, chat__id=chat_id, type=PeerType.CHAT).select_related("owner", "chat")

    @classmethod
    async def from_input_peer(cls, user: models.User, input_peer: InputPeers) -> Peer | None:
        if isinstance(input_peer, InputUserSelf):
            input_peer = InputPeerSelf()
        elif isinstance(input_peer, InputUser):
            input_peer = InputPeerUser(user_id=input_peer.user_id, access_hash=input_peer.access_hash)

        if isinstance(input_peer, InputPeerSelf) \
                or (isinstance(input_peer, InputPeerUser) and input_peer.user_id == user.id):
            peer, _ = await Peer.get_or_create(owner=user, type=PeerType.SELF, user=None)
            return peer
        elif isinstance(input_peer, InputPeerUser):
            return await Peer.get_or_none(
                owner=user, user__id=input_peer.user_id, access_hash=input_peer.access_hash,
            ).select_related("owner", "user")
        elif isinstance(input_peer, InputPeerChat):
            return await Peer.get_or_none(owner=user, chat__id=input_peer.chat_id).select_related("owner", "chat")

        raise ErrorRpc(error_code=400, error_message="PEER_ID_NOT_SUPPORTED")

    async def get_opposite(self) -> list[Peer]:
        if self.type is PeerType.USER:
            if self.user_id == 777000:
                return []
            peer, created = await Peer.get_or_create(type=PeerType.USER, owner=self.user, user=self.owner)
            if peer.blocked:
                return []
            if not created:
                await peer.fetch_related("owner")
            return [peer]
        elif self.type is PeerType.CHAT:
            return await Peer.filter(
                type=PeerType.CHAT, owner__id__not=self.owner.id,
            ).select_related("owner", "chat")

        return []

    def to_tl(self) -> PeerUser | PeerChat:
        if self.type is PeerType.SELF:
            return PeerUser(user_id=self.owner_id)
        if self.type is PeerType.USER:
            return PeerUser(user_id=self.user_id)
        if self.type == PeerType.CHAT:
            return PeerChat(chat_id=self.chat_id)

        assert False, "unknown peer type"
