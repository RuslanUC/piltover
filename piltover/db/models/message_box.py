from __future__ import annotations

from typing import TypeVar, Generic, TypeGuard

from tortoise import Model, fields

from piltover.db import models
from piltover.db.models.utils import NullableFK

OwnerT = TypeVar("OwnerT", bound="models.User | None")
UserT = TypeVar("UserT", bound="models.User | None")
ChatT = TypeVar("ChatT", bound="models.Chat | None")
ChannelT = TypeVar("ChannelT", bound="models.Channel | None")
OwnerIdT = TypeVar("OwnerIdT", bound=int | None)
UserIdT = TypeVar("UserIdT", bound=int | None)
ChatIdT = TypeVar("ChatIdT", bound=int | None)
ChannelIdT = TypeVar("ChannelIdT", bound=int | None)


class MessageBox(Model, Generic[OwnerT, UserT, ChatT, ChannelT, OwnerIdT, UserIdT, ChatIdT, ChannelIdT]):
    id: int = fields.BigIntField(primary_key=True)
    sequence: int = fields.BigIntField(default=1)
    owner: OwnerT = NullableFK("models.User", related_name="owned_messagebox")
    user: UserT = NullableFK("models.User")
    chat: ChatT = NullableFK("models.Chat")
    channel: ChannelT = fields.OneToOneField("models.Channel", null=True, default=None)

    class Meta:
        unique_together = (
            ("owner", "user",),
            ("owner", "chat",),
        )

    owner_id: OwnerIdT
    user_id: UserIdT
    chat_id: ChatIdT
    channel_id: ChannelIdT

    @staticmethod
    def is_self(box: MessageBox) -> TypeGuard[MessageBox[models.User, models.User, None, None, int, int, None, None]]:
        return box.owner_id is not None and box.user_id is not None and box.owner_id == box.user_id

    @staticmethod
    def is_user(box: MessageBox) -> TypeGuard[MessageBox[models.User, models.User, None, None, int, int, None, None]]:
        return box.owner_id is not None and box.user_id is not None and box.owner_id != box.user_id

    @staticmethod
    def is_chat(box: MessageBox) -> TypeGuard[MessageBox[models.User, None, models.Chat, None, int, None, int, None]]:
        return box.owner_id is not None and box.chat_id is not None

    @staticmethod
    def is_channel(box: MessageBox) -> TypeGuard[MessageBox[None, None, None, models.Channel, None, None, None, int]]:
        return box.channel_id is not None
