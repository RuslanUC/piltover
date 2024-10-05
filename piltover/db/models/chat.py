from __future__ import annotations

from tortoise import fields
from tortoise.functions import Count

from piltover.db import models
from piltover.db.enums import ChatType
from piltover.db.models._utils import Model
from piltover.exceptions import ErrorRpc
from piltover.tl import PeerUser, InputPeerUser as TLInputPeerUser, InputPeerSelf as TLInputPeerSelf


class Chat(Model):
    id: int = fields.BigIntField(pk=True)
    type: ChatType = fields.IntEnumField(ChatType)

    # noforwards: bool = fields.BooleanField(default=False)
    # title: str = fields.CharField(max_length=128, null=True, default=None)
    # created_at: datetime = fields.DatetimeField(default=datetime.now)
    # TODO: add other fields, e.g. photo, username (if channel or group), etc.

    # owner: models.User = fields.ForeignKeyField("models.User", null=True, default=None, on_delete=fields.SET_NULL)

    dialogs: fields.ReverseRelation[models.Dialog]

    async def get_other_user(self, current_user: models.User) -> models.User | None:
        other_dialog = await (models.Dialog.get_or_none(chat=self, user__id__not=current_user.id)
                              .select_related("user"))
        return other_dialog.user if other_dialog is not None else None

    async def get_peer(self, current_user: models.User):
        peer = PeerUser(user_id=0)
        if self.type == ChatType.SAVED:
            return PeerUser(user_id=current_user.id)
        if self.type == ChatType.PRIVATE:
            user = await self.get_other_user(current_user) or current_user
            peer = PeerUser(user_id=user.id)
        # elif self.chat.type == ChatType.GROUP:
        #    peer = PeerChat(chat_id=self.chat.id)
        # elif self.chat.type == ChatType.CHANNEL:
        #    peer = PeerChannel(channel_id=self.chat.id)

        return peer

    @staticmethod
    async def get_private(user1: models.User, user2: models.User | None = None) -> Chat | None:
        if user2 is None or user1 == user2:
            return await Chat.get_or_none(type=ChatType.SAVED, dialogs__user__id=user1.id)
        return await (Chat.get_or_none(type=ChatType.PRIVATE, dialogs__user__id__in=[user1.id, user2.id])
                      .annotate(user_count=Count("dialogs__user__id", distinct=True))
                      .filter(user_count=2)
                      .group_by("id"))

    @staticmethod
    async def get_or_create_private(user1: models.User, user2: models.User | None = None) -> Chat:
        chat = await Chat.get_private(user1, user2)
        if chat is None:
            chat = await Chat.create(type=ChatType.PRIVATE if user2 is not None or user1 == user2 else ChatType.SAVED)
            await models.Dialog.create(user=user1, chat=chat)
            if user2 is not None:
                await models.Dialog.create(user=user2, chat=chat)

        return chat

    @classmethod
    async def from_input_peer(
            cls, user: models.User, peer: TLInputPeerUser | TLInputPeerSelf, create: bool = False
    ) -> Chat | None:
        if isinstance(peer, TLInputPeerUser) and peer.user_id == user.id:
            peer = TLInputPeerSelf()

        if isinstance(peer, TLInputPeerSelf):
            chat = await Chat.get_or_create_private(user) if create else await Chat.get_private(user)
        elif isinstance(peer, TLInputPeerUser):
            if (to_user := await models.User.get_or_none(id=peer.user_id)) is None:
                raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")
            chat = await Chat.get_or_create_private(user, to_user) if create else await Chat.get_private(user, to_user)
        else:
            raise ErrorRpc(error_code=400, error_message="PEER_ID_NOT_SUPPORTED")

        return chat

    async def to_tl_users_chats(self, user: models.User, existing_users) -> tuple[dict, None]:
        users = {}
        if self.type in {ChatType.PRIVATE, ChatType.SAVED}:
            peer = await self.get_peer(user)
            if peer.user_id not in existing_users and peer.user_id not in users:
                users[peer.user_id] = await (await models.User.get(id=peer.user_id)).to_tl(user)

        return users, None
