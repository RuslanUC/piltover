from __future__ import annotations

from datetime import datetime
from os import urandom

from tortoise import fields, Model
from tortoise.expressions import Q

from piltover.db import models
from piltover.db.enums import PeerType
from piltover.exceptions import ErrorRpc
from piltover.tl import PeerUser, InputPeerUser, InputPeerSelf, InputUserSelf, InputUser, PeerChat, InputPeerChat, \
    InputUserEmpty, InputPeerEmpty, InputPeerChannel, InputChannelEmpty, InputChannel, PeerChannel


def gen_access_hash() -> int:
    return int.from_bytes(urandom(8)) >> 2


InputPeers = InputPeerSelf | InputPeerUser | InputUserSelf | InputUser | InputPeerChat | InputChannel \
             | InputChannelEmpty | InputPeerChannel


class Peer(Model):
    id: int = fields.BigIntField(pk=True)
    owner: models.User = fields.ForeignKeyField("models.User", related_name="owner", null=True)
    type: PeerType = fields.IntEnumField(PeerType)
    access_hash: int = fields.BigIntField(default=gen_access_hash)
    blocked_at: datetime = fields.DatetimeField(null=True, default=None)

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
            return None

        if isinstance(input_peer, (InputPeerSelf, InputUserSelf)) \
                or (isinstance(input_peer, (InputPeerUser, InputUser)) and input_peer.user_id == user.id):
            peer, _ = await Peer.get_or_create(owner=user, type=PeerType.SELF, user=None)
            peer.owner = await peer.owner
            return peer
        elif isinstance(input_peer, (InputPeerUser, InputUser)):
            return await Peer.get_or_none(
                owner=user, user__id=input_peer.user_id, access_hash=input_peer.access_hash,
            ).select_related("owner", "user")
        elif isinstance(input_peer, InputPeerChat):
            return await Peer.get_or_none(owner=user, chat__id=input_peer.chat_id).select_related("owner", "chat")
        elif isinstance(input_peer, (InputPeerChannel, InputChannel)):
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
            if peer.blocked_at is not None:
                return []
            if not created:
                await peer.fetch_related("owner")
            return [peer]
        elif self.type is PeerType.CHAT:
            return await Peer.filter(
                type=PeerType.CHAT, owner__id__not=self.owner.id, chat__id=self.chat_id,
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

        raise RuntimeError("Unreachable")

    def to_input_peer(
            self, self_is_user: bool = False,
    ) -> InputPeerSelf | InputPeerUser | InputPeerChat | InputPeerChannel:
        if self.type is PeerType.SELF:
            if self_is_user:
                return InputPeerUser(user_id=self.owner_id, access_hash=self.access_hash)
            return InputPeerSelf()
        if self.type is PeerType.USER:
            return InputPeerUser(user_id=self.user_id, access_hash=self.access_hash)
        if self.type == PeerType.CHAT:
            return InputPeerChat(chat_id=self.chat_id)
        if self.type == PeerType.CHANNEL:
            return InputPeerChannel(channel_id=self.channel_id, access_hash=self.access_hash)

        raise RuntimeError("Unreachable")

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

    @property
    def chat_or_channel(self) -> models.ChatBase:
        if self.type is PeerType.CHAT:
            return self.chat
        elif self.type is PeerType.CHANNEL:
            return self.channel

        raise RuntimeError(f".chat_or_channel called on peer with type {self.type}")
