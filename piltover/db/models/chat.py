from __future__ import annotations

from tortoise import fields
from tortoise.functions import Count

from piltover.db import models
from piltover.db.enums import ChatType
from piltover.db.models._utils import Model
from piltover.tl_new import PeerUser


class Chat(Model):
    id: int = fields.BigIntField(pk=True)
    type: ChatType = fields.IntEnumField(ChatType)

    # noforwards: bool = fields.BooleanField(default=False)
    # title: str = fields.CharField(max_length=128, null=True, default=None)
    # created_at: datetime = fields.DatetimeField(default=datetime.now)
    # TODO: add other fields, e.g. photo, username (if channel or group), etc.

    # owner: models.User = fields.ForeignKeyField("models.User", null=True, default=None, on_delete=fields.SET_NULL)

    dialogs: fields.ReverseRelation[models.Dialog]

    async def get_peer(self, current_user: models.User):
        peer = PeerUser(user_id=0)
        if self.type == ChatType.SAVED:
            return PeerUser(user_id=current_user.id)
        if self.type == ChatType.PRIVATE:
            other_dialog = await (models.Dialog.get_or_none(chat=self, user__id__not=current_user.id)
                                  .select_related("user"))
            peer = PeerUser(user_id=(other_dialog.user if other_dialog is not None else current_user).id)
        # elif self.chat.type == ChatType.GROUP:
        #    peer = PeerChat(chat_id=self.chat.id)
        # elif self.chat.type == ChatType.CHANNEL:
        #    peer = PeerChannel(channel_id=self.chat.id)

        return peer

    @staticmethod
    async def get_private(user1: models.User, user2: models.User | None = None) -> Chat | None:
        if user2 is None:
            return await Chat.get_or_none(type=ChatType.SAVED, dialogs__user__id=user1.id)
        return await (Chat.get_or_none(type=ChatType.PRIVATE, dialogs__user__id__in=[user1.id, user2.id])
                      .annotate(user_count=Count("dialogs__user__id", distinct=True))
                      .filter(user_count=2)
                      .group_by("id"))

    @staticmethod
    async def get_or_create_private(user1: models.User, user2: models.User | None = None) -> Chat:
        chat = await Chat.get_private(user1, user2)
        if chat is not None:
            chat = await Chat.create(type=ChatType.PRIVATE if user2 is not None else ChatType.SAVED)
            await models.Dialog.create(user=user1, chat=chat)
            if user2 is not None:
                await models.Dialog.create(user=user2, chat=chat)

        return chat
