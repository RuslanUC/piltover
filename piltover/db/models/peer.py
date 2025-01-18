from __future__ import annotations

from os import urandom

from tortoise import fields, Model

from piltover.db import models
from piltover.db.enums import PeerType
from piltover.exceptions import ErrorRpc
from piltover.tl import PeerUser, InputPeerUser, InputPeerSelf, InputUserSelf, InputUser, PeerChat, InputPeerChat, \
    User as TLUser, Chat as TLChat, InputUserEmpty, InputPeerEmpty


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
    async def from_chat_id_raise(cls, user: models.User, chat_id: int, message: str = "CHAT_ID_INVALID") -> Peer:
        if (peer := await Peer.from_chat_id(user, chat_id)) is not None:
            return peer
        raise ErrorRpc(error_code=400, error_message=message)

    @classmethod
    async def from_input_peer(cls, user: models.User, input_peer: InputPeers) -> Peer | None:
        if isinstance(input_peer, (InputUserEmpty, InputPeerEmpty)):
            return

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

    def to_tl(self) -> PeerUser | PeerChat:
        if self.type is PeerType.SELF:
            return PeerUser(user_id=self.owner_id)
        if self.type is PeerType.USER:
            return PeerUser(user_id=self.user_id)
        if self.type == PeerType.CHAT:
            return PeerChat(chat_id=self.chat_id)

        assert False, "unknown peer type"

    # TODO: replace with collect_users_chats ?
    async def tl_users_chats(
            self, user: models.User, users: dict[int, TLUser] | None = None, chats: dict[int, TLChat] | None = None
    ) -> tuple[dict[int, TLUser] | None, dict[int, TLChat] | None]:
        ret = users, chats

        if self.type is PeerType.SELF:
            if users is None or self.owner_id in users:
                return ret
            self.owner = await self.owner
            users[self.owner.id] = await self.owner.to_tl(user)
        elif self.type is PeerType.USER:
            if users is None or self.user_id in users:
                return ret
            self.user = await self.user
            users[self.user.id] = await self.user.to_tl(user)
        elif self.type is PeerType.CHAT:
            if chats is None or self.chat_id in chats:
                return ret
            self.chat = await self.chat
            chats[self.chat.id] = await self.chat.to_tl(user)

        return ret

    async def collect_users_chats(
            self, current_user: models.User, users: dict[int, TLUser] | None = None,
            chats: dict[int, TLChat] | None = None
    ) -> tuple[dict[int, TLUser] | None, dict[int, TLChat] | None]:
        if users is not None \
                and self.type is PeerType.CHAT \
                and self.chat is not None \
                and self.chat_id is not None \
                and chats is not None \
                and self.chat_id not in chats:
            participants = await models.User.filter(
                chatparticipants__chat__id=self.chat_id, id__not_in=list(users.keys())
            )
            for participant in participants:
                users[participant.id] = await participant.to_tl(current_user)


        return await self.tl_users_chats(current_user, users, chats)
