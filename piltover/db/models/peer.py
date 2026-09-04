from __future__ import annotations

from datetime import datetime
from typing import TypeVar, TypeGuard, TypeAlias, cast, Protocol

from pypika_tortoise import Parameter, Dialects
from tortoise import fields, Model, Tortoise
from tortoise.expressions import Q
from tortoise.queryset import QuerySetSingle

from piltover.context import request_ctx
from piltover.db import models
from piltover.db.enums import PeerType, MessageType
from piltover.exceptions import ErrorRpc, Unreachable
from piltover.tl import PeerUser, InputPeerUser, InputPeerSelf, InputUserSelf, InputUser, PeerChat, InputPeerChat, \
    InputUserEmpty, InputPeerEmpty, InputPeerChannel, InputChannelEmpty, InputChannel, PeerChannel, InputUserFromMessage
from piltover.tl.base import InputUser as InputUserBase, InputPeer as InputPeerBase, InputChannel as InputChannelBase

InputPeers = InputPeerBase | InputUserBase | InputChannelBase
InputOnlyPeers = InputPeerSelf | InputPeerUser | InputPeerChat | InputPeerChannel

OwnerT = TypeVar("OwnerT", bound="models.User | None", covariant=True)
UserT = TypeVar("UserT", bound="models.User | None", covariant=True)
ChatT = TypeVar("ChatT", bound="models.Chat | None", covariant=True)
ChannelT = TypeVar("ChannelT", bound="models.Channel | None", covariant=True)
OwnerIdT = TypeVar("OwnerIdT", bound=int | None, covariant=True)
UserIdT = TypeVar("UserIdT", bound=int | None, covariant=True)
ChatIdT = TypeVar("ChatIdT", bound=int | None, covariant=True)
ChannelIdT = TypeVar("ChannelIdT", bound=int | None, covariant=True)


class PeerProtocolMin(Protocol[OwnerIdT, UserIdT, ChatIdT, ChannelIdT]):
    @property
    def owner_id(self) -> OwnerIdT: ...

    @property
    def user_id(self) -> UserIdT: ...

    @property
    def chat_id(self) -> ChatIdT: ...

    @property
    def channel_id(self) -> ChannelIdT: ...


PeerProtocolMinSelfT: TypeAlias = PeerProtocolMin[int, int, None, None]
PeerProtocolMinUserT: TypeAlias = PeerProtocolMin[int, int, None, None]
PeerProtocolMinChatT: TypeAlias = PeerProtocolMin[int, None, int, None]
PeerProtocolMinChannelT: TypeAlias = PeerProtocolMin[None, None, None, int]
PeerProtocolMinOwnedT: TypeAlias = PeerProtocolMin[int, int | None, int | None, int | None]


def peer_is_self_min(peer: PeerProtocolMin) -> TypeGuard[PeerProtocolMinSelfT]:
    return peer.owner_id is not None and peer.user_id is not None and peer.owner_id == peer.user_id


def peer_is_user_min(peer: PeerProtocolMin) -> TypeGuard[PeerProtocolMinUserT]:
    return peer.owner_id is not None and peer.user_id is not None and peer.owner_id != peer.user_id


def peer_is_self_or_user_min(peer: PeerProtocolMin) -> TypeGuard[PeerProtocolMinChatT]:
    return peer.owner_id is not None and peer.user_id is not None


def peer_is_chat_min(peer: PeerProtocolMin) -> TypeGuard[PeerProtocolMinChatT]:
    return peer.owner_id is not None and peer.chat_id is not None


def peer_is_channel_min(peer: PeerProtocolMin) -> TypeGuard[PeerProtocolMinChannelT]:
    return peer.owner_id is None and peer.channel_id is not None


def peer_is_owned_min(peer: PeerProtocolMin) -> TypeGuard[PeerProtocolMinOwnedT]:
    return peer.owner_id is not None


class PeerProtocolFull(
    PeerProtocolMin[OwnerIdT, UserIdT, ChatIdT, ChannelIdT],
    Protocol[UserT, ChatT, ChannelT, OwnerIdT, UserIdT, ChatIdT, ChannelIdT],
):
    @property
    def user(self) -> UserT: ...

    @property
    def chat(self) -> ChatT: ...

    @property
    def channel(self) -> ChannelT: ...


PeerProtocolFullSelfT: TypeAlias = PeerProtocolFull["models.User", None, None, int, int, None, None]
PeerProtocolFullUserT: TypeAlias = PeerProtocolFull["models.User", None, None, int, int, None, None]
PeerProtocolFullChatT: TypeAlias = PeerProtocolFull[None, "models.Chat", None, int, None, int, None]
PeerProtocolFullChannelT: TypeAlias = PeerProtocolFull[None, None, "models.Channel", None, None, None, int]
PeerProtocolFullOwnedT: TypeAlias = PeerProtocolFull["models.User | None", "models.Chat | None", "models.Channel | None", int, int | None, int | None, int | None]  # noqa: E501


def peer_is_self(peer: PeerProtocolFull) -> TypeGuard[PeerProtocolFullSelfT]:
    if not peer_is_full(peer):
        raise RuntimeError("Expected full peer, got min")
    return bool(peer_is_self_min(peer))


def peer_is_user(peer: PeerProtocolFull) -> TypeGuard[PeerProtocolFullUserT]:
    if not peer_is_full(peer):
        raise RuntimeError("Expected full peer, got min")
    return bool(peer_is_user_min(peer))


def peer_is_self_or_user(peer: PeerProtocolFull) -> TypeGuard[PeerProtocolFullUserT]:
    if not peer_is_full(peer):
        raise RuntimeError("Expected full peer, got min")
    return bool(peer_is_self_or_user_min(peer))


def peer_is_chat(peer: PeerProtocolFull) -> TypeGuard[PeerProtocolFullChatT]:
    if not peer_is_full(peer):
        raise RuntimeError("Expected full peer, got min")
    return bool(peer_is_chat_min(peer))


def peer_is_channel(peer: PeerProtocolFull) -> TypeGuard[PeerProtocolFullChannelT]:
    if not peer_is_full(peer):
        raise RuntimeError("Expected full peer, got min")
    return bool(peer_is_channel_min(peer))


def peer_is_owned(peer: PeerProtocolFull) -> TypeGuard[PeerProtocolFullOwnedT]:
    if not peer_is_full(peer):
        raise RuntimeError("Expected full peer, got min")
    return bool(peer_is_owned_min(peer))


def peer_is_full(peer: PeerProtocolMin) -> TypeGuard[PeerProtocolFull]:
    return hasattr(peer, "user") and hasattr(peer, "chat") and hasattr(peer, "channel")


_LAST_MESSAGE_SYNC_SQL = f"""
UPDATE peer
SET
    last_message_id = (
        SELECT m.id
        FROM messageref m
        INNER JOIN messagecontent mc ON m.content_id = mc.id
        WHERE m.peer_id = peer.id AND mc.type != {MessageType.SCHEDULED.value} 
        ORDER BY m.id DESC
        LIMIT 1
    ),
    last_message_date = (
        SELECT mc.date
        FROM messageref m
        INNER JOIN messagecontent mc ON m.content_id = mc.id
        WHERE m.peer_id = peer.id AND mc.type != {MessageType.SCHEDULED.value} 
        ORDER BY m.id DESC
        LIMIT 1
    )
WHERE {{where_condition}};
"""


class Peer(Model):
    id: int = fields.BigIntField(primary_key=True)
    owner: models.User = fields.ForeignKeyField("models.User", related_name="owner", null=True)
    type: PeerType = fields.IntEnumField(PeerType, description="")
    blocked_at: datetime | None = fields.DatetimeField(null=True, default=None)
    user_ttl_period_days: int | None = fields.SmallIntField(null=True, default=None)
    user_has_wallpaper: bool = fields.BooleanField(default=False)
    last_message_id: int | None = fields.BigIntField(null=True, default=None, db_index=True)
    last_message_date: datetime | None = fields.DatetimeField(null=True, default=None, db_index=True)
    out_max_read_id: int = fields.BigIntField(default=0)

    user: models.User = fields.ForeignKeyField("models.User", related_name="user", null=True, default=None)
    chat: models.Chat = fields.ForeignKeyField("models.Chat", null=True, default=None)
    channel: models.Channel = fields.OneToOneField("models.Channel", null=True, default=None, related_name="peer")

    class Meta:
        unique_together = (
            ("owner", "user",),
            ("owner", "chat",),
        )

    owner_id: int | None
    user_id: int | None
    chat_id: int | None
    channel_id: int | None

    @classmethod
    async def from_chat_id_raise(
            cls, user_id: int, chat_id: int, message: str = "CHAT_ID_INVALID", allow_migrated: bool = False,
            select_related: tuple[str, ...] | None = None,
    ) -> Peer:
        chat_id = models.Chat.norm_id(chat_id)
        query = Q(owner_id=user_id, chat_id=chat_id, chat__deleted=False)
        if not allow_migrated:
            query &= Q(chat__migrated=False)

        if select_related is None:
            select_related = ()

        if (peer := await Peer.get_or_none(query).select_related("chat", *select_related)) is not None:
            return peer
        raise ErrorRpc(error_code=400, error_message=message)

    @classmethod
    def type_and_id_from_input(cls, user_id: int, input_peer: InputPeers) -> tuple[PeerType, int] | None:
        if isinstance(input_peer, (InputUserEmpty, InputPeerEmpty, InputChannelEmpty)):
            return None

        auth_id = cast(int, request_ctx.get().auth_id)

        if isinstance(input_peer, (InputPeerSelf, InputUserSelf)) \
                or (isinstance(input_peer, (InputPeerUser, InputUser)) and input_peer.user_id == user_id):
            return PeerType.SELF, user_id

        if isinstance(input_peer, (InputPeerUser, InputUser)):
            if not models.User.check_access_hash(user_id, auth_id, input_peer.user_id, input_peer.access_hash):
                return None
            return PeerType.USER, input_peer.user_id

        if isinstance(input_peer, InputPeerChat):
            chat_id = models.Chat.norm_id(input_peer.chat_id)
            return PeerType.CHAT, chat_id

        if isinstance(input_peer, (InputPeerChannel, InputChannel)):
            channel_id = models.Channel.norm_id(input_peer.channel_id)
            if not models.Channel.check_access_hash(user_id, auth_id, channel_id, input_peer.access_hash):
                return None
            return PeerType.CHANNEL, channel_id

        raise ErrorRpc(error_code=400, error_message="PEER_ID_NOT_SUPPORTED")

    @classmethod
    def type_and_id_from_input_raise(
            cls, user_id: int, input_peer: InputPeers, error_message: str = "PEER_ID_INVALID", error_code: int = 400,
    ) -> tuple[PeerType, int]:
        if (peer_info := cls.type_and_id_from_input(user_id, input_peer)) is not None:
            return peer_info
        raise ErrorRpc(error_code=error_code, error_message=error_message)

    @classmethod
    def query_from_input_peer(
            cls, user: models.User | int, input_peer: InputPeers, allow_bot: bool = True,
            allow_migrated_chat: bool = False, peer_types: tuple[PeerType, ...] | None = None,
    ) -> QuerySetSingle[Peer | None] | None:
        if isinstance(input_peer, (InputUserEmpty, InputPeerEmpty, InputChannelEmpty)):
            return None

        user_id = user.id if isinstance(user, models.User) else user

        auth_id = cast(int, request_ctx.get().auth_id)

        if isinstance(input_peer, (InputPeerSelf, InputUserSelf)) \
                or (isinstance(input_peer, (InputPeerUser, InputUser)) and input_peer.user_id == user_id):
            if peer_types is not None and PeerType.SELF not in peer_types:
                return None
            return Peer.get(owner_id=user_id, user_id=user_id)

        if isinstance(input_peer, (InputPeerUser, InputUser)):
            if peer_types is not None and PeerType.USER not in peer_types:
                return None
            if not models.User.check_access_hash(user_id, auth_id, input_peer.user_id, input_peer.access_hash):
                return None
            query = Q(owner_id=user_id, user_id=input_peer.user_id)
            if not allow_bot:
                query &= Q(user__bot=False)
            return Peer.get_or_none(query)

        if isinstance(input_peer, InputPeerChat):
            if peer_types is not None and PeerType.CHAT not in peer_types:
                return None
            chat_id = models.Chat.norm_id(input_peer.chat_id)
            query = Q(owner_id=user_id, chat_id=chat_id, chat__deleted=False)
            if not allow_migrated_chat:
                query &= Q(chat__migrated=False)
            return Peer.get_or_none(query)

        if isinstance(input_peer, (InputPeerChannel, InputChannel)):
            if peer_types is not None and PeerType.CHANNEL not in peer_types:
                return None
            channel_id = models.Channel.norm_id(input_peer.channel_id)
            if not models.Channel.check_access_hash(user_id, auth_id, channel_id, input_peer.access_hash):
                return None
            return Peer.get_or_none(channel_id=channel_id, channel__deleted=False)

        raise ErrorRpc(error_code=400, error_message="PEER_ID_NOT_SUPPORTED")

    @classmethod
    async def _from_input_peer(
            cls, user: models.User | int, input_peer: InputPeers, allow_bot: bool = True,
            allow_migrated_chat: bool = False, peer_types: tuple[PeerType, ...] | None = None,
            select_related: tuple[str, ...] | None = None, select_user_username: bool = False,
    ) -> Peer | None:
        query = cls.query_from_input_peer(user, input_peer, allow_bot, allow_migrated_chat, peer_types)
        if query is None:
            return None

        user_id = user.id if isinstance(user, models.User) else user

        if select_related is None:
            select_related = ()

        if isinstance(input_peer, (InputPeerSelf, InputUserSelf)) \
                or (isinstance(input_peer, (InputPeerUser, InputUser)) and input_peer.user_id == user_id):
            return await query.select_related("user")

        if isinstance(input_peer, (InputPeerUser, InputUser)):
            if peer_types is not None and PeerType.USER not in peer_types:
                return None
            if select_user_username:
                select_related = *select_related, "user__username"
            return await query.select_related("owner", "user", *select_related)

        if isinstance(input_peer, InputPeerChat):
            if peer_types is not None and PeerType.CHAT not in peer_types:
                return None
            return await query.select_related("chat", *select_related)

        if isinstance(input_peer, (InputPeerChannel, InputChannel)):
            if peer_types is not None and PeerType.CHANNEL not in peer_types:
                return None
            return await query.select_related("channel", *select_related)

        raise ErrorRpc(error_code=400, error_message="PEER_ID_NOT_SUPPORTED")

    @classmethod
    async def from_input_peer_raise(
            cls, user: models.User | int, peer: InputPeers, message: str = "PEER_ID_INVALID", code: int = 400,
            allow_migrated_chat: bool = False, peer_types: tuple[PeerType, ...] | None = None,
            select_related: tuple[str, ...] | None = None, select_user_username: bool = False,
    ) -> Peer:
        peer_ = await cls._from_input_peer(
            user, peer, allow_migrated_chat=allow_migrated_chat, peer_types=peer_types, select_related=select_related,
            select_user_username=select_user_username,
        )
        if peer_ is not None:
            return peer_
        raise ErrorRpc(error_code=code, error_message=message)

    async def get_opposite(self, allow_blocked: bool = False) -> list[Peer]:
        if self.type is PeerType.USER:
            if self.user_id == 777000:
                return []
            peer, created = await Peer.get_or_create(
                owner_id=self.user_id, user_id=self.owner_id, defaults={"type": PeerType.USER},
            )
            if peer.blocked_at is not None and not allow_blocked:
                return []
            peer.user = self.owner
            peer.owner = self.user
            return [peer]
        elif self.type is PeerType.CHAT:
            return await Peer.filter(owner_id__not=self.owner_id, chat_id=self.chat_id)

        return []

    def to_tl(self) -> PeerUser | PeerChat | PeerChannel:
        if peer_is_self(self):
            return PeerUser(user_id=self.owner_id)
        if peer_is_user(self):
            return PeerUser(user_id=self.user_id)
        if peer_is_chat(self):
            return PeerChat(chat_id=models.Chat.make_id_from(self.chat_id))
        if peer_is_channel(self):
            return PeerChannel(channel_id=models.Channel.make_id_from(self.channel_id))

        raise Unreachable

    def target_id_raw(self) -> int:
        if peer_is_self(self):
            return self.user_id
        if peer_is_user(self):
            return self.user_id
        if peer_is_chat(self):
            return self.chat_id
        if peer_is_channel(self):
            return self.channel_id

        raise Unreachable

    def to_input_peer(self, self_is_user: bool = False) -> InputOnlyPeers:
        if peer_is_self(self):
            if self_is_user:
                return InputPeerUser(user_id=self.user_id, access_hash=-1)
            return InputPeerSelf()
        if peer_is_user(self):
            return InputPeerUser(user_id=self.user_id, access_hash=-1)
        if peer_is_chat(self):
            return InputPeerChat(chat_id=models.Chat.make_id_from(self.chat_id))
        if peer_is_channel(self):
            return InputPeerChannel(channel_id=models.Channel.make_id_from(self.channel_id), access_hash=-1)

        raise Unreachable

    @property
    def chat_or_channel(self) -> models.ChatBase:
        if self.type is PeerType.CHAT:
            return self.chat
        elif self.type is PeerType.CHANNEL:
            return self.channel

        raise RuntimeError(f".chat_or_channel called on peer with type {self.type}")

    def __repr__(self) -> str:
        obj_fields = [f"type={self.type!r}"]
        if (peer_id := getattr(self, "id")) is not None:
            obj_fields.append(f"id={peer_id!r}")
        if (owner_id := getattr(self, "owner_id")) is not None:
            obj_fields.append(f"owner_id={owner_id!r}")

        if peer_is_self_or_user(self):
            obj_fields.append(f"user_id={self.user_id}")
        elif peer_is_chat(self):
            obj_fields.append(f"chat_id={self.chat_id}")
        elif peer_is_channel(self):
            obj_fields.append(f"channel_id={self.channel_id}")
        else:
            raise Unreachable

        return f"{self.__class__.__name__}({', '.join(obj_fields)})"

    @staticmethod
    def input_is_self(user_id: int, input_peer: InputUserBase | InputPeerBase) -> bool:
        if isinstance(input_peer, (InputUserSelf, InputPeerSelf)):
            return True
        if isinstance(input_peer, (InputPeerUser, InputUser, InputUserFromMessage)):
            return input_peer.user_id == user_id
        return False

    @classmethod
    def query_from_input_user_or_raise(
            cls, user_id: int, input_user: InputUserBase | InputPeerBase, auth_id: int | None = None,
            error_message: str = "PEER_ID_INVALID",
    ) -> QuerySetSingle[Peer]:
        if auth_id is None:
            ctx = request_ctx.get()
            auth_id = ctx.auth_id

        peer_query = Peer.filter(owner_id=user_id)

        if Peer.input_is_self(user_id, input_user):
            return peer_query.get(user_id=user_id)
        elif isinstance(input_user, (InputUser, InputPeerUser)):
            if not models.User.check_access_hash(user_id, auth_id, input_user.user_id, input_user.access_hash):
                raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")
            return peer_query.get(user_id=input_user.user_id)
        else:
            raise ErrorRpc(error_code=400, error_message=error_message)

    def tup(self) -> tuple[PeerType, int]:
        return self.type, self.target_id_raw()

    async def sync_last_message(self) -> None:
        await self.sync_last_message_bulk([self])

    @classmethod
    async def sync_last_message_bulk(cls, peers: list[Peer | int]) -> None:
        if not peers:
            return

        peer_ids = [(peer.id if isinstance(peer, Peer) else peer) for peer in peers]

        conn = Tortoise.get_connection("default")
        dialect = Dialects(conn.capabilities.dialect)
        placeholder_factory = Parameter.IDX_PLACEHOLDERS[dialect]
        placeholders = [placeholder_factory(i + 1) for i in range(len(peer_ids))]

        if len(peer_ids) == 1:
            where_condition = f"peer.id = {placeholders[0]}"
        else:
            where_condition = f"peer.id IN ({','.join(placeholders)})"

        sql = _LAST_MESSAGE_SYNC_SQL.format(where_condition=where_condition)
        await conn.execute_query(sql, peer_ids)

    async def update_max_read_id(self, new_max_read_id: int) -> None:
        if self.out_max_read_id >= new_max_read_id:
            return
        await Peer.filter(id=self.id, out_max_read_id__lt=new_max_read_id).update(out_max_read_id=new_max_read_id)
        self.out_max_read_id = new_max_read_id

    def can_see_reactions_list(self) -> bool:
        return (
                self.type in (PeerType.SELF, PeerType.USER, PeerType.CHAT)
                or (self.type is PeerType.CHANNEL and self.channel.supergroup)
        )


class PeerMinimalMin:
    __slots__ = ("owner_id", "user_id", "chat_id", "channel_id",)

    def __init__(
            self,
            *,
            owner_id: int | None = None,
            user_id: int | None = None,
            chat_id: int | None = None,
            channel_id: int | None = None,
    ) -> None:
        self.owner_id = owner_id
        self.user_id = user_id
        self.chat_id = chat_id
        self.channel_id = channel_id


class PeerMinimalFull(PeerMinimalMin):
    __slots__ = ("user", "chat", "channel", "owner_id", "user_id", "chat_id", "channel_id",)

    def __init__(
            self,
            *,
            user: models.User | None = None,
            chat: models.Chat | None = None,
            channel: models.Channel | None = None,
            owner_id: int | None = None,
            user_id: int | None = None,
            chat_id: int | None = None,
            channel_id: int | None = None,
    ) -> None:
        super().__init__(owner_id=owner_id, user_id=user_id, chat_id=chat_id, channel_id=channel_id)
        self.user = user
        self.chat = chat
        self.channel = channel

        if user is not None:
            self.user_id = user.id
        elif chat is not None:
            self.chat_id = chat.id
        elif channel is not None:
            self.channel_id = channel.id
        else:
            raise ValueError("At least one of \"user\", \"chat\", \"channel\" must be passed.")
