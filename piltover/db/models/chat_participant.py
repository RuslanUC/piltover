from __future__ import annotations

from datetime import datetime

from tortoise import fields, Model

from piltover.db import models
from piltover.db.enums import ChatBannedRights
from piltover.db.models._utils import IntFlagField
from piltover.tl import ChatParticipant as TLChatParticipant, ChatParticipantCreator, ChatParticipantAdmin


class ChatParticipant(Model):
    id: int = fields.BigIntField(pk=True)
    user: models.User = fields.ForeignKeyField("models.User")
    chat: models.Chat = fields.ForeignKeyField("models.Chat")
    inviter_id: int = fields.BigIntField(default=0)
    invited_at: datetime = fields.DatetimeField(auto_now_add=True)
    is_admin: bool = fields.BooleanField(default=False)
    banned_until: datetime = fields.DatetimeField(null=True, default=None)
    banned_rights: ChatBannedRights = IntFlagField(ChatBannedRights, default=0)
    invite: models.ChatInvite | None = fields.ForeignKeyField("models.ChatInvite", null=True, default=None, on_delete=fields.SET_NULL)

    user_id: int
    chat_id: int

    class Meta:
        unique_together = (
            ("user", "chat",),
        )

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
