from __future__ import annotations

from datetime import datetime

from tortoise import fields, Model
from tortoise.expressions import Q

from piltover.context import request_ctx
from piltover.db import models
from piltover.db.enums import PeerType
from piltover.exceptions import ErrorRpc, Unreachable
from piltover.tl import PeerUser, InputPeerUser, InputPeerSelf, InputUserSelf, InputUser, PeerChat, InputPeerChat, \
    InputUserEmpty, InputPeerEmpty, InputPeerChannel, InputChannelEmpty, InputChannel, PeerChannel


InputPeers = InputPeerSelf | InputPeerUser | InputUserSelf | InputUser | InputPeerChat | InputChannel \
             | InputChannelEmpty | InputPeerChannel


class Peer(Model):
    id: int = fields.BigIntField(pk=True)
    owner: models.User = fields.ForeignKeyField("models.User", related_name="owner", null=True)
    type: PeerType = fields.IntEnumField(PeerType)
    blocked_at: datetime = fields.DatetimeField(null=True, default=None)
    user_ttl_period_days: int | None = fields.SmallIntField(null=True, default=None)

    user: models.User | None = fields.ForeignKeyField("models.User", related_name="user", null=True, default=None)
    chat: models.Chat | None = fields.ForeignKeyField("models.Chat", null=True, default=None)
    channel: models.Channel | None = fields.ForeignKeyField("models.Channel", null=True, default=None)

    class Meta:
        unique_together = (
            ("owner", "user",),
            ("owner", "chat",),
            ("owner", "channel",),
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
    async def from_chat_id(cls, user: models.User, chat_id: int, allow_migrated: bool = False) -> Peer | None:
        chat_id = models.Chat.norm_id(chat_id)
        query = Q(owner=user, chat__id=chat_id, type=PeerType.CHAT)
        if not allow_migrated:
            query &= Q(chat__migrated=False)
        return await Peer.get_or_none(query).select_related("owner", "chat")

    @classmethod
    async def from_chat_id_raise(
            cls, user: models.User, chat_id: int, message: str = "CHAT_ID_INVALID", allow_migrated: bool = False,
    ) -> Peer:
        if (peer := await Peer.from_chat_id(user, chat_id, allow_migrated)) is not None:
            return peer
        raise ErrorRpc(error_code=400, error_message=message)

    @classmethod
    async def from_input_peer(
            cls, user: models.User, input_peer: InputPeers, allow_bot: bool = True, allow_migrated_chat: bool = False,
            peer_types: tuple[PeerType, ...] | None = None,
    ) -> Peer | None:
        if isinstance(input_peer, (InputUserEmpty, InputPeerEmpty, InputChannelEmpty)):
            return None

        ctx = request_ctx.get()

        if isinstance(input_peer, (InputPeerSelf, InputUserSelf)) \
                or (isinstance(input_peer, (InputPeerUser, InputUser)) and input_peer.user_id == user.id):
            if peer_types is not None and PeerType.SELF not in peer_types:
                return None
            peer, _ = await Peer.get_or_create(owner=user, type=PeerType.SELF, user=user)
            peer.owner = await peer.owner
            return peer

        if isinstance(input_peer, (InputPeerUser, InputUser)):
            if peer_types is not None and PeerType.USER not in peer_types:
                return None
            if not models.User.check_access_hash(user.id, ctx.auth_id, input_peer.user_id, input_peer.access_hash):
                return None
            query = Q(owner=user, user__id=input_peer.user_id)
            if not allow_bot:
                query &= Q(user__bot=False)
            return await Peer.get_or_none(query).select_related("owner", "user")

        if isinstance(input_peer, InputPeerChat):
            if peer_types is not None and PeerType.CHAT not in peer_types:
                return None
            chat_id = models.Chat.norm_id(input_peer.chat_id)
            query = Q(owner=user, chat__id=chat_id)
            if not allow_migrated_chat:
                query &= Q(chat__migrated=False)
            return await Peer.get_or_none(query).select_related("owner", "chat")

        if isinstance(input_peer, (InputPeerChannel, InputChannel)):
            if peer_types is not None and PeerType.CHANNEL not in peer_types:
                return None
            channel_id = models.Channel.norm_id(input_peer.channel_id)
            if not models.Channel.check_access_hash(user.id, ctx.auth_id, channel_id, input_peer.access_hash):
                return None
            return await Peer.get_or_none(
                owner=user, channel__id=channel_id, channel__deleted=False,
            ).select_related("owner", "channel")

        raise ErrorRpc(error_code=400, error_message="PEER_ID_NOT_SUPPORTED")

    @classmethod
    async def from_input_peer_raise(
            cls, user: models.User, peer: InputPeers, message: str = "PEER_ID_INVALID", code: int = 400,
            allow_migrated_chat: bool = False, peer_types: tuple[PeerType, ...] | None = None,
    ) -> Peer:
        peer_ = await Peer.from_input_peer(user, peer, allow_migrated_chat=allow_migrated_chat, peer_types=peer_types)
        if peer_ is not None:
            return peer_
        raise ErrorRpc(error_code=code, error_message=message)

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

    async def get_for_user(self, for_user: models.User) -> Peer | None:
        if for_user.id == self.owner_id:
            return self
        if self.type is PeerType.SELF or self.type is PeerType.USER:
            return await Peer.get_or_none(
                owner=for_user, user__id=self.user_id,
            ).select_related("owner", "user")
        elif self.type is PeerType.CHAT:
            return await Peer.get_or_none(
                type=PeerType.CHAT, owner=for_user, chat__id=self.chat_id,
            ).select_related("owner", "chat")
        elif self.type is PeerType.CHANNEL:
            return await Peer.get_or_none(
                type=PeerType.CHANNEL, owner=for_user, channel__id=self.channel_id,
            ).select_related("owner", "channel")
        raise Unreachable

    def to_tl(self) -> PeerUser | PeerChat | PeerChannel:
        if self.type is PeerType.SELF:
            return PeerUser(user_id=self.owner_id)
        if self.type is PeerType.USER:
            return PeerUser(user_id=self.user_id)
        if self.type == PeerType.CHAT:
            return PeerChat(chat_id=models.Chat.make_id_from(self.chat_id))
        if self.type == PeerType.CHANNEL:
            return PeerChannel(channel_id=models.Channel.make_id_from(self.channel_id))

        raise Unreachable

    def to_input_peer(
            self, self_is_user: bool = False,
    ) -> InputPeerSelf | InputPeerUser | InputPeerChat | InputPeerChannel:
        if self.type is PeerType.SELF:
            if self_is_user:
                return InputPeerUser(user_id=self.owner_id, access_hash=-1)
            return InputPeerSelf()
        if self.type is PeerType.USER:
            return InputPeerUser(user_id=self.user_id, access_hash=-1)
        if self.type == PeerType.CHAT:
            return InputPeerChat(chat_id=models.Chat.make_id_from(self.chat_id))
        if self.type == PeerType.CHANNEL:
            return InputPeerChannel(channel_id=models.Channel.make_id_from(self.channel_id), access_hash=-1)

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
