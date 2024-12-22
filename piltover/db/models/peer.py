from __future__ import annotations

from os import urandom

from tortoise import fields

from piltover.db import models
from piltover.db.enums import PeerType
from piltover.db.models._utils import Model
from piltover.exceptions import ErrorRpc
from piltover.tl import PeerUser, InputPeerUser, InputPeerSelf, InputUserSelf, InputUser


def gen_access_hash() -> int:
    return int.from_bytes(urandom(8)) >> 2


InputPeers = InputPeerSelf | InputPeerUser | InputUserSelf | InputUser


class Peer(Model):
    id: int = fields.BigIntField(pk=True)
    owner: models.User = fields.ForeignKeyField("models.User", related_name="owner")
    type: PeerType = fields.IntEnumField(PeerType)
    access_hash: int = fields.BigIntField(default=gen_access_hash)

    user: models.User | None = fields.ForeignKeyField("models.User", related_name="user", null=True, default=None)
    #chat: models.Chat | None = fields.ForeignKeyField("models.Chat", null=True, default=None)

    class Meta:
        unique_together = (
            ("owner", "type", "user"),
        )

    owner_id: int
    user_id: int

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

        raise ErrorRpc(error_code=400, error_message="PEER_ID_NOT_SUPPORTED")

    async def get_opposite(self) -> list[Peer]:
        if self.type is PeerType.USER:
            peer, _ = await Peer.get_or_create(type=PeerType.USER, owner=self.user, user=self.owner)
            return [peer]

        return []

    def to_tl(self) -> PeerUser:
        if self.type is PeerType.SELF:
            return PeerUser(user_id=self.owner_id)
        if self.type is PeerType.USER:
            return PeerUser(user_id=self.user_id)

        assert False, "unknown peer type"
