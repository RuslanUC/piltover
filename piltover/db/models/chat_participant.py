from __future__ import annotations

from datetime import datetime

from tortoise import fields, Model

from piltover.db import models
from piltover.db.enums import ChatBannedRights, ChatAdminRights
from piltover.db.models._utils import IntFlagField
from piltover.tl import ChatParticipant as TLChatParticipant, ChatParticipantCreator, ChatParticipantAdmin, \
    ChannelParticipant, ChannelParticipantSelf, ChannelParticipantCreator, ChannelParticipantAdmin, \
    ChannelParticipantBanned, ChannelParticipantLeft

ChannelParticipants = ChannelParticipant | ChannelParticipantSelf | ChannelParticipantCreator \
                      | ChannelParticipantAdmin | ChannelParticipantBanned | ChannelParticipantLeft


class ChatParticipant(Model):
    id: int = fields.BigIntField(pk=True)
    user: models.User = fields.ForeignKeyField("models.User")
    chat: models.Chat | None = fields.ForeignKeyField("models.Chat", null=True, default=None)
    channel: models.Channel | None = fields.ForeignKeyField("models.Channel", null=True, default=None)
    inviter_id: int = fields.BigIntField(default=0)
    invited_at: datetime = fields.DatetimeField(auto_now_add=True)
    is_admin: bool = fields.BooleanField(default=False)
    banned_until: datetime = fields.DatetimeField(null=True, default=None)
    banned_rights: ChatBannedRights = IntFlagField(ChatBannedRights, default=ChatBannedRights(0))
    admin_rights: ChatAdminRights = IntFlagField(ChatAdminRights, default=ChatAdminRights(0))
    invite: models.ChatInvite | None = fields.ForeignKeyField("models.ChatInvite", null=True, default=None, on_delete=fields.SET_NULL)
    admin_rank: str = fields.CharField(max_length=24, default="")
    promoted_by_id: int = fields.BigIntField(default=0)

    user_id: int
    chat_id: int | None
    channel_id: int | None

    class Meta:
        unique_together = (
            ("user", "chat",),
            ("user", "channel",),
        )

    @property
    def chat_or_channel(self) -> models.Chat | models.Channel:
        if self.chat_id is not None:
            return self.chat
        elif self.channel_id is not None:
            return self.channel

        raise RuntimeError("Unreachable")

    async def to_tl(self) -> TLChatParticipant | ChatParticipantCreator | ChatParticipantAdmin:
        self.chat = await self.chat

        if self.user_id == self.chat.creator_id:
            return ChatParticipantCreator(user_id=self.user_id)
        elif self.is_admin:
            return ChatParticipantAdmin(
                user_id=self.user_id, inviter_id=self.inviter_id, date=int(self.invited_at.timestamp())
            )

        return TLChatParticipant(
            user_id=self.user_id, inviter_id=self.inviter_id, date=int(self.invited_at.timestamp())
        )

    async def to_tl_channel(self, user: models.User) -> ChannelParticipants:
        self.channel = await self.channel

        if self.user_id == self.chat.creator_id:
            return ChannelParticipantCreator(
                user_id=self.user_id, admin_rights=ChatAdminRights.all().to_tl(), rank=self.admin_rank or None,
            )
        elif self.is_admin:
            return ChannelParticipantAdmin(
                user_id=self.user_id, inviter_id=self.inviter_id, date=int(self.invited_at.timestamp()),
                is_self=self.user_id == user.id, promoted_by=self.promoted_by_id, rank=self.admin_rank or None,
                admin_rights=self.admin_rights.to_tl(), can_edit=bool(self.admin_rights & ChatAdminRights.ADD_ADMINS),
            )
        elif self.user_id == user.id:
            return ChannelParticipantSelf(
                user_id=self.user_id, inviter_id=self.inviter_id, date=int(self.invited_at.timestamp())
            )

        return ChannelParticipant(user_id=self.user_id, date=int(self.invited_at.timestamp()))
