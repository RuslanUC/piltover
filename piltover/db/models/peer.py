from __future__ import annotations

from os import urandom

from tortoise import fields, Model
from tortoise.expressions import Q

from piltover.db import models
from piltover.db.enums import PeerType
from piltover.db.models._utils import fetch_users_chats
from piltover.exceptions import ErrorRpc
from piltover.tl import PeerUser, InputPeerUser, InputPeerSelf, InputUserSelf, InputUser, PeerChat, InputPeerChat, \
    User as TLUser, Chat as TLChat, InputUserEmpty, InputPeerEmpty, InputPeerChannel, InputChannelEmpty, InputChannel, \
    PeerChannel, Channel as TLChannel


def gen_access_hash() -> int:
    return int.from_bytes(urandom(8)) >> 2


InputPeers = InputPeerSelf | InputPeerUser | InputUserSelf | InputUser | InputPeerChat | InputChannel \
             | InputChannelEmpty | InputPeerChannel


class Peer(Model):
    id: int = fields.BigIntField(pk=True)
    owner: models.User = fields.ForeignKeyField("models.User", related_name="owner", null=True)
    type: PeerType = fields.IntEnumField(PeerType)
    access_hash: int = fields.BigIntField(default=gen_access_hash)
    blocked: bool = fields.BooleanField(default=False)

    user: models.User | None = fields.ForeignKeyField("models.User", related_name="user", null=True, default=None)
    chat: models.Chat | None = fields.ForeignKeyField("models.Chat", null=True, default=None)
    channel: models.Channel | None = fields.ForeignKeyField("models.Channel", null=True, default=None)

    class Meta:
        unique_together = (
            ("owner", "type", "user", "chat", "channel",),
        )

    owner_id: int
    user_id: int
    chat_id: int
    channel_id: int

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
    async def from_chat_id_raise(cls, user: models.User, chat_id: int, message: str = "CHAT_ID_INVALID") -> Peer:
        if (peer := await Peer.from_chat_id(user, chat_id)) is not None:
            return peer
        raise ErrorRpc(error_code=400, error_message=message)

    @classmethod
    async def from_input_peer(cls, user: models.User, input_peer: InputPeers) -> Peer | None:
        if isinstance(input_peer, (InputUserEmpty, InputPeerEmpty, InputChannelEmpty)):
            return

        if isinstance(input_peer, InputUserSelf):
            input_peer = InputPeerSelf()
        elif isinstance(input_peer, InputUser):
            input_peer = InputPeerUser(user_id=input_peer.user_id, access_hash=input_peer.access_hash)
        elif isinstance(input_peer, InputChannel):
            input_peer = InputPeerChannel(channel_id=input_peer.channel_id, access_hash=input_peer.access_hash)

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
        elif isinstance(input_peer, InputPeerChannel):
            return await Peer.get_or_none(
                owner=user, channel__id=input_peer.channel_id, access_hash=input_peer.access_hash,
            ).select_related("owner", "channel")

        raise ErrorRpc(error_code=400, error_message="PEER_ID_NOT_SUPPORTED")

    @classmethod
    async def from_input_peer_raise(cls, user: models.User, peer: InputPeers, message: str = "PEER_ID_INVALID") -> Peer:
        if (peer_ := await Peer.from_input_peer(user, peer)) is not None:
            return peer_
        raise ErrorRpc(error_code=400, error_message=message)

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

    def to_tl(self) -> PeerUser | PeerChat | PeerChannel:
        if self.type is PeerType.SELF:
            return PeerUser(user_id=self.owner_id)
        if self.type is PeerType.USER:
            return PeerUser(user_id=self.user_id)
        if self.type == PeerType.CHAT:
            return PeerChat(chat_id=self.chat_id)
        if self.type == PeerType.CHANNEL:
            return PeerChannel(channel_id=self.channel_id)

        assert False, "unknown peer type"

    @classmethod
    def query_users_chats_cls(
            cls, peer_id: int, users: Q | None = None, chats: Q | None = None, channels: Q | None = None,
            peer_type: PeerType | None = None
    ) -> tuple[Q | None, Q | None, Q | None]:
        ret = users, chats, channels

        if (peer_type is PeerType.SELF and users is None) \
                or (peer_type is PeerType.USER and users is None) \
                or (peer_type is PeerType.CHAT and chats is None) \
                or (peer_type is PeerType.CHANNEL and channels is None):
            return ret

        if users is not None and (peer_type is None or peer_type is PeerType.SELF):
            users |= Q(owner__id=peer_id, owner__type=PeerType.SELF)
        if users is not None and (peer_type is None or peer_type is PeerType.USER):
            users |= Q(user__id=peer_id, user__type=PeerType.USER)
        if chats is not None and (peer_type is None or peer_type is PeerType.CHAT):
            chats |= Q(peers__id=peer_id, peers__type=PeerType.CHAT)
            if users is not None:
                users |= Q(chatparticipants__chat__peers__id=peer_id, chatparticipants__chat__peers__type=PeerType.CHAT)
        if channels is not None and (peer_type is None or peer_type is PeerType.CHANNEL):
            channels |= Q(peers__id=peer_id, peers__type=PeerType.CHANNEL)

        return users, chats, channels

    def query_users_chats(
            self, users: Q | None = None, chats: Q | None = None, channels: Q | None = None,
    ) -> tuple[Q | None, Q | None, Q | None]:
        return Peer.query_users_chats_cls(self.id, users, chats, channels, self.type)
        #ret = users, chats, channels

        #if self.type is PeerType.SELF:
        #    if users is None:
        #        return ret
        #    users |= Q(owner__id=self.id)
        #elif self.type is PeerType.USER:
        #    if users is None:
        #        return ret
        #    users |= Q(user__id=self.id)
        #elif self.type is PeerType.CHAT:
        #    if chats is None:
        #        return ret

        #    chats |= Q(peers__id=self.id)
        #    users |= Q(chatparticipants__chat__peers__id=self.id)
        #elif self.type is PeerType.CHANNEL:
        #    if channels is None:
        #        return ret
        #    channels |= Q(peers__id=self.id)

        #return users, chats, channels

    @property
    def chat_or_channel(self) -> models.ChatBase:
        if self.type is PeerType.CHAT:
            return self.chat
        elif self.type is PeerType.CHANNEL:
            return self.channel

        raise RuntimeError(f".chat_or_channel called on peer with type {self.type}")
