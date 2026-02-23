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
InputOnlyPeers = InputPeerSelf | InputPeerUser | InputPeerChat | InputPeerChannel


class Peer(Model):
    id: int = fields.BigIntField(pk=True)
    owner: models.User = fields.ForeignKeyField("models.User", related_name="owner", null=True)
    type: PeerType = fields.IntEnumField(PeerType, description="")
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
            return await Peer.get(owner=user, type=PeerType.SELF)
        return await Peer.get_or_none(owner=user, user_id=user_id, type=PeerType.USER).select_related("user")

    @classmethod
    async def from_chat_id(
            cls, user: models.User, chat_id: int, allow_migrated: bool = False,
            select_related: tuple[str, ...] | None = None,
    ) -> Peer | None:
        chat_id = models.Chat.norm_id(chat_id)
        query = Q(owner=user, chat_id=chat_id, type=PeerType.CHAT)
        if not allow_migrated:
            query &= Q(chat__migrated=False)

        if select_related is None:
            select_related = ()

        return await Peer.get_or_none(query).select_related("owner", "chat", *select_related)

    @classmethod
    async def from_chat_id_raise(
            cls, user: models.User, chat_id: int, message: str = "CHAT_ID_INVALID", allow_migrated: bool = False,
            select_related: tuple[str, ...] | None = None,
    ) -> Peer:
        if (peer := await Peer.from_chat_id(user, chat_id, allow_migrated, select_related)) is not None:
            return peer
        raise ErrorRpc(error_code=400, error_message=message)

    @classmethod
    async def from_input_peer(
            cls, user: models.User, input_peer: InputPeers, allow_bot: bool = True, allow_migrated_chat: bool = False,
            peer_types: tuple[PeerType, ...] | None = None, select_related: tuple[str, ...] | None = None,
    ) -> Peer | None:
        if isinstance(input_peer, (InputUserEmpty, InputPeerEmpty, InputChannelEmpty)):
            return None

        ctx = request_ctx.get()

        if select_related is None:
            select_related = ()

        if isinstance(input_peer, (InputPeerSelf, InputUserSelf)) \
                or (isinstance(input_peer, (InputPeerUser, InputUser)) and input_peer.user_id == user.id):
            if peer_types is not None and PeerType.SELF not in peer_types:
                return None
            peer = await Peer.get(owner=user, type=PeerType.SELF, user=user)
            peer.owner = peer.user = user
            return peer

        if isinstance(input_peer, (InputPeerUser, InputUser)):
            if peer_types is not None and PeerType.USER not in peer_types:
                return None
            if not models.User.check_access_hash(user.id, ctx.auth_id, input_peer.user_id, input_peer.access_hash):
                return None
            query = Q(owner=user, user_id=input_peer.user_id)
            if not allow_bot:
                query &= Q(user__bot=False)
            return await Peer.get_or_none(query).select_related("owner", "user", *select_related)

        if isinstance(input_peer, InputPeerChat):
            if peer_types is not None and PeerType.CHAT not in peer_types:
                return None
            chat_id = models.Chat.norm_id(input_peer.chat_id)
            query = Q(owner=user, chat_id=chat_id)
            if not allow_migrated_chat:
                query &= Q(chat__migrated=False)
            return await Peer.get_or_none(query).select_related("owner", "chat", *select_related)

        if isinstance(input_peer, (InputPeerChannel, InputChannel)):
            if peer_types is not None and PeerType.CHANNEL not in peer_types:
                return None
            channel_id = models.Channel.norm_id(input_peer.channel_id)
            if not models.Channel.check_access_hash(user.id, ctx.auth_id, channel_id, input_peer.access_hash):
                return None
            return await Peer.get_or_none(
                owner=user, channel_id=channel_id, channel__deleted=False,
            ).select_related("owner", "channel", *select_related)

        raise ErrorRpc(error_code=400, error_message="PEER_ID_NOT_SUPPORTED")

    @classmethod
    async def from_input_peer_raise(
            cls, user: models.User, peer: InputPeers, message: str = "PEER_ID_INVALID", code: int = 400,
            allow_migrated_chat: bool = False, peer_types: tuple[PeerType, ...] | None = None,
            select_related: tuple[str, ...] | None = None,
    ) -> Peer:
        peer_ = await Peer.from_input_peer(
            user, peer, allow_migrated_chat=allow_migrated_chat, peer_types=peer_types, select_related=select_related,
        )
        if peer_ is not None:
            return peer_
        raise ErrorRpc(error_code=code, error_message=message)

    async def get_opposite(self, allow_blocked: bool = False) -> list[Peer]:
        if self.type is PeerType.USER:
            if self.user_id == 777000:
                return []
            peer, created = await Peer.get_or_create(type=PeerType.USER, owner=self.user, user=self.owner)
            if peer.blocked_at is not None and not allow_blocked:
                return []
            if not created:
                peer.owner = self.user
            return [peer]
        elif self.type is PeerType.CHAT:
            return await Peer.filter(
                type=PeerType.CHAT, owner_id__not=self.owner.id, chat_id=self.chat_id,
            ).select_related("owner", "chat")

        return []

    async def get_for_user(self, for_user: models.User) -> Peer | None:
        if for_user.id == self.owner_id:
            return self
        if self.type is PeerType.SELF or self.type is PeerType.USER:
            return await Peer.get_or_none(
                owner=for_user, user_id=self.user_id,
            ).select_related("owner", "user")
        elif self.type is PeerType.CHAT:
            return await Peer.get_or_none(
                type=PeerType.CHAT, owner=for_user, chat_id=self.chat_id,
            ).select_related("owner", "chat")
        elif self.type is PeerType.CHANNEL:
            return await Peer.get_or_none(
                type=PeerType.CHANNEL, owner=for_user, channel_id=self.channel_id,
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

    def target_id_raw(self) -> int:
        if self.type is PeerType.SELF:
            return self.user_id
        if self.type is PeerType.USER:
            return self.user_id
        if self.type == PeerType.CHAT:
            return self.chat_id
        if self.type == PeerType.CHANNEL:
            return self.channel_id

        raise Unreachable

    def to_input_peer(self, self_is_user: bool = False) -> InputOnlyPeers:
        return self.to_input_peer_cls(self.type, self.user_id, self.chat_id, self.channel_id, self_is_user)

    @classmethod
    def to_input_peer_cls(
            cls, type_: PeerType, user_id: int | None, chat_id: int | None, channel_id: int | None,
            self_is_user: bool = False,
    ) -> InputOnlyPeers:
        if type_ is PeerType.SELF:
            if self_is_user:
                return InputPeerUser(user_id=user_id, access_hash=-1)
            return InputPeerSelf()
        if type_ is PeerType.USER:
            return InputPeerUser(user_id=user_id, access_hash=-1)
        if type_ == PeerType.CHAT:
            return InputPeerChat(chat_id=models.Chat.make_id_from(chat_id))
        if type_ == PeerType.CHANNEL:
            return InputPeerChannel(channel_id=models.Channel.make_id_from(channel_id), access_hash=-1)

        raise RuntimeError("Unreachable")

    @property
    def chat_or_channel(self) -> models.ChatBase:
        if self.type is PeerType.CHAT:
            return self.chat
        elif self.type is PeerType.CHANNEL:
            return self.channel

        raise RuntimeError(f".chat_or_channel called on peer with type {self.type}")

    def query_chat_or_channel(self) -> dict:
        if self.type is PeerType.CHAT:
            return {"chat_id": self.chat_id}
        if self.type is PeerType.CHANNEL:
            return {"channel_id": self.channel_id}

        raise NotImplementedError

    def q_this_or_channel(self) -> Q:
        if self.type is PeerType.CHANNEL:
            return Q(peer__owner=None, peer__channel_id=self.channel_id)
        return Q(peer=self)

    def q_this_and_channel(self) -> Q:
        q = Q(peer=self)
        if self.type is PeerType.CHANNEL:
            q |= Q(peer__owner=None, peer__channel_id=self.channel_id)
        return q

    def __repr__(self) -> str:
        if self.type in (PeerType.SELF, PeerType.USER):
            peer_id = f"user_id={self.user_id}"
        elif self.type is PeerType.CHAT:
            peer_id = f"chat_id={self.chat_id}"
        elif self.type is PeerType.CHANNEL:
            peer_id = f"channel_id={self.channel_id}"
        else:
            raise Unreachable

        return f"{self.__class__.__name__}(id={self.id!r}, owner_id={self.owner_id!r}, type={self.type!r}, {peer_id})"
