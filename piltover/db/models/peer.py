from __future__ import annotations

from datetime import datetime
from typing import TypeVar, Generic, TYPE_CHECKING, Literal, TypeGuard, TypeAlias, cast

from pypika_tortoise import Parameter, Dialects
from tortoise import fields, Model, Tortoise
from tortoise.expressions import Q
from tortoise.queryset import QuerySetSingle

from piltover.context import request_ctx
from piltover.db import models
from piltover.db.enums import PeerType
from piltover.exceptions import ErrorRpc, Unreachable
from piltover.tl import PeerUser, InputPeerUser, InputPeerSelf, InputUserSelf, InputUser, PeerChat, InputPeerChat, \
    InputUserEmpty, InputPeerEmpty, InputPeerChannel, InputChannelEmpty, InputChannel, PeerChannel, InputUserFromMessage
from piltover.tl.base import InputUser as InputUserBase, InputPeer as InputPeerBase, InputChannel as InputChannelBase

InputPeers = InputPeerBase | InputUserBase | InputChannelBase
InputOnlyPeers = InputPeerSelf | InputPeerUser | InputPeerChat | InputPeerChannel

OwnerT = TypeVar("OwnerT", bound="models.User | None")
UserT = TypeVar("UserT", bound="models.User | None")
ChatT = TypeVar("ChatT", bound="models.Chat | None")
ChannelT = TypeVar("ChannelT", bound="models.Channel | None")
OwnerIdT = TypeVar("OwnerIdT", bound=int | None)
UserIdT = TypeVar("UserIdT", bound=int | None)
ChatIdT = TypeVar("ChatIdT", bound=int | None)
ChannelIdT = TypeVar("ChannelIdT", bound=int | None)
AnyPeerType = Literal[PeerType.SELF, PeerType.USER, PeerType.CHAT, PeerType.CHANNEL]
PeerTypeT = TypeVar(
    "PeerTypeT",
    bound=AnyPeerType,
)

PeerSelfT: TypeAlias = "Peer[models.User, models.User, None, None, int, int, None, None, Literal[PeerType.SELF]]"  # noqa: E501
PeerUserT: TypeAlias = "Peer[models.User, models.User, None, None, int, int, None, None, Literal[PeerType.USER]]"  # noqa: E501
PeerChatT: TypeAlias = "Peer[models.User, None, models.Chat, None, int, None, int, None, Literal[PeerType.CHAT]]"  # noqa: E501
PeerChannelT: TypeAlias = "Peer[None, None, None, models.Channel, None, None, None, int, Literal[PeerType.CHANNEL]]"  # noqa: E501
PeerOwnedT: TypeAlias = "Peer[models.User, models.User | None, models.Chat | None, models.Channel | None, int, int | None, int | None, int | None, AnyPeerType]"  # noqa: E501

_LAST_MESSAGE_SYNC_SQL = """
UPDATE peer
SET
    last_message_id = (
        SELECT m.id
        FROM messageref m
        INNER JOIN messagecontent mc ON m.content_id = mc.id
        WHERE m.peer_id = peer.id
        ORDER BY m.id DESC
        LIMIT 1
    ),
    last_message_date = (
        SELECT mc.date
        FROM messageref m
        INNER JOIN messagecontent mc ON m.content_id = mc.id
        WHERE m.peer_id = peer.id
        ORDER BY m.id DESC
        LIMIT 1
    )
WHERE {where_condition};
"""


class Peer(Model, Generic[OwnerT, UserT, ChatT, ChannelT, OwnerIdT, UserIdT, ChatIdT, ChannelIdT, PeerTypeT]):
    id: int = fields.BigIntField(primary_key=True)
    owner: models.User = fields.ForeignKeyField("models.User", related_name="owner", null=True)
    type: PeerTypeT = fields.IntEnumField(PeerType, description="")
    blocked_at: datetime | None = fields.DatetimeField(null=True, default=None)
    user_ttl_period_days: int | None = fields.SmallIntField(null=True, default=None)
    user_has_wallpaper: bool = fields.BooleanField(default=False)
    last_message_id: int | None = fields.BigIntField(null=True, default=None, db_index=True)
    last_message_date: datetime | None = fields.DatetimeField(null=True, default=None, db_index=True)
    out_max_read_id: int = fields.BigIntField(default=0)

    user: UserT = fields.ForeignKeyField("models.User", related_name="user", null=True, default=None)
    chat: ChatT = fields.ForeignKeyField("models.Chat", null=True, default=None)
    channel: ChannelT = fields.OneToOneField("models.Channel", null=True, default=None, related_name="peer")

    class Meta:
        unique_together = (
            ("owner", "user",),
            ("owner", "chat",),
        )

    owner_id: OwnerIdT
    user_id: UserIdT
    chat_id: ChatIdT
    channel_id: ChannelIdT

    # PyCharm cant properly infer None without this
    if TYPE_CHECKING:
        @property
        def type(self) -> PeerTypeT: raise Unreachable
        @property
        def owner(self) -> OwnerT: raise Unreachable
        @property
        def user(self) -> UserT: raise Unreachable
        @property
        def chat(self) -> ChatT: raise Unreachable
        @property
        def channel(self) -> ChannelT: raise Unreachable
        @property
        def owner_id(self) -> OwnerIdT: raise Unreachable
        @property
        def user_id(self) -> UserIdT: raise Unreachable
        @property
        def chat_id(self) -> ChatIdT: raise Unreachable
        @property
        def channel_id(self) -> ChannelIdT: raise Unreachable

        @type.setter
        def type(self, value: PeerType) -> None: ...
        @owner.setter
        def owner(self, value: models.User | None) -> None: ...
        @user.setter
        def user(self, value: models.User | None) -> None: ...
        @chat.setter
        def chat(self, value: models.Chat | None) -> None: ...
        @channel.setter
        def channel(self, value: models.Channel | None) -> None: ...
        @owner_id.setter
        def owner_id(self, value: int | None) -> None: ...
        @user_id.setter
        def user_id(self, value: int | None) -> None: ...
        @chat_id.setter
        def chat_id(self, value: int | None) -> None: ...
        @channel_id.setter
        def channel_id(self, value: int | None) -> None: ...

    @staticmethod
    def is_self(peer: Peer) -> TypeGuard[PeerSelfT]:
        return peer.owner_id is not None and peer.user_id is not None and peer.owner_id == peer.user_id

    @staticmethod
    def is_user(peer: Peer) -> TypeGuard[PeerUserT]:
        return peer.owner_id is not None and peer.user_id is not None and peer.owner_id != peer.user_id

    @staticmethod
    def is_chat(peer: Peer) -> TypeGuard[PeerChatT]:
        return peer.owner_id is not None and peer.chat_id is not None

    @staticmethod
    def is_channel(peer: Peer) -> TypeGuard[PeerChannelT]:
        return peer.owner_id is None and peer.channel_id is not None

    @staticmethod
    def is_owned(peer: Peer) -> TypeGuard[PeerOwnedT]:
        return peer.owner_id is not None

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

    def __repr__(self) -> str:
        if self.type in (PeerType.SELF, PeerType.USER):
            peer_id = f"user_id={self.user_id}"
        elif self.type is PeerType.CHAT:
            peer_id = f"chat_id={self.chat_id}"
        elif self.type is PeerType.CHANNEL:
            peer_id = f"channel_id={self.channel_id}"
        else:
            raise Unreachable

        id_maybe = f"id={self.id!r}, " if hasattr(self, "id") else ""
        owner_id_maybe = f"owner_id={self.owner_id!r}, " if hasattr(self, "owner_id") else ""
        return f"{self.__class__.__name__}({id_maybe}{owner_id_maybe}type={self.type!r}, {peer_id})"

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
