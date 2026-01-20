from __future__ import annotations

from datetime import datetime
from typing import cast

from tortoise import fields, Model
from tortoise.expressions import Subquery
from tortoise.functions import Count
from tortoise.queryset import QuerySet

from piltover.db import models
from piltover.db.enums import ChatBannedRights, ChatAdminRights
from piltover.db.models.utils import IntFlagField
from piltover.tl import ChatParticipant as TLChatParticipant, ChatParticipantCreator, ChatParticipantAdmin, \
    ChannelParticipant, ChannelParticipantSelf, ChannelParticipantCreator, ChannelParticipantAdmin, \
    ChannelParticipantBanned, ChannelParticipantLeft, PeerUser

ChannelParticipants = ChannelParticipant | ChannelParticipantSelf | ChannelParticipantCreator \
                      | ChannelParticipantAdmin | ChannelParticipantBanned | ChannelParticipantLeft


class ChatParticipant(Model):
    id: int = fields.BigIntField(pk=True)
    user: models.User = fields.ForeignKeyField("models.User")
    chat: models.Chat | None = fields.ForeignKeyField("models.Chat", null=True, default=None)
    channel: models.Channel | None = fields.ForeignKeyField("models.Channel", null=True, default=None)
    inviter_id: int = fields.BigIntField(default=0)
    invited_at: datetime = fields.DatetimeField(auto_now_add=True)
    banned_until: datetime = fields.DatetimeField(null=True, default=None)
    banned_rights: ChatBannedRights = IntFlagField(ChatBannedRights, default=ChatBannedRights(0))
    admin_rights: ChatAdminRights = IntFlagField(ChatAdminRights, default=ChatAdminRights(0))
    invite: models.ChatInvite | None = fields.ForeignKeyField("models.ChatInvite", null=True, default=None, on_delete=fields.SET_NULL)
    admin_rank: str = fields.CharField(max_length=24, default="")
    promoted_by_id: int = fields.BigIntField(default=0)
    min_message_id: int | None = fields.BigIntField(null=True, default=None)
    left: bool = fields.BooleanField(default=False)

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

    @property
    def chat_or_channel_id(self) -> int:
        if self.chat_id is not None:
            return self.chat_id
        elif self.channel_id is not None:
            return self.channel_id

        raise RuntimeError("Unreachable")

    @property
    def is_admin(self) -> bool:
        return cast(int, self.admin_rights.value) > 0

    async def to_tl(
            self, chat_creator_id: int | None = None
    ) -> TLChatParticipant | ChatParticipantCreator | ChatParticipantAdmin:
        if chat_creator_id is None:
            self.chat = await self.chat
            chat_creator_id = self.chat.creator_id

        return self.to_tl_chat_with_creator(chat_creator_id)

    def to_tl_chat_with_creator(
            self, chat_creator_id: int,
    ) -> TLChatParticipant | ChatParticipantCreator | ChatParticipantAdmin:
        if self.user_id == chat_creator_id:
            return ChatParticipantCreator(user_id=self.user_id)
        elif self.is_admin:
            return ChatParticipantAdmin(
                user_id=self.user_id, inviter_id=self.inviter_id, date=int(self.invited_at.timestamp()),
            )

        return TLChatParticipant(
            user_id=self.user_id, inviter_id=self.inviter_id, date=int(self.invited_at.timestamp()),
        )

    async def to_tl_channel(self, user: models.User, creator_id: int | None = None) -> ChannelParticipants:
        if creator_id is None:
            self.channel = await self.channel
            creator_id = self.channel.creator_id

        return self.to_tl_channel_with_creator(user, creator_id)

    def to_tl_channel_with_creator(self, user: models.User, creator_id: int) -> ChannelParticipants:
        if self.user_id == creator_id:
            return ChannelParticipantCreator(
                user_id=self.user_id,
                admin_rights=self.admin_rights.to_tl(),
                rank=self.admin_rank or None,
            )
        elif self.is_admin:
            return ChannelParticipantAdmin(
                user_id=self.user_id,
                inviter_id=self.inviter_id,
                date=int(self.invited_at.timestamp()),
                is_self=self.user_id == user.id,
                promoted_by=self.promoted_by_id,
                rank=self.admin_rank or None,
                admin_rights=self.admin_rights.to_tl(),
                can_edit=bool(self.admin_rights & ChatAdminRights.ADD_ADMINS),
            )
        elif self.banned_rights:
            return ChannelParticipantBanned(
                left=self.left,
                peer=PeerUser(user_id=self.user_id),
                kicked_by=0,  # TODO: add this as model field
                date=int(self.invited_at.timestamp()),
                banned_rights=self.banned_rights.to_tl(),
            )
        elif self.user_id == user.id:
            return ChannelParticipantSelf(
                user_id=self.user_id,
                inviter_id=self.inviter_id,
                date=int(self.invited_at.timestamp()),
            )

        return ChannelParticipant(
            user_id=self.user_id,
            date=int(self.invited_at.timestamp()),
        )

    @classmethod
    def common_chats_query(cls, user_id: int, other_user_id: int) -> QuerySet[ChatParticipant]:
        # TODO: uncomment when https://github.com/tortoise/tortoise-orm/issues/2058 is resolved
        #return ChatParticipant.filter(
        #    chat__id__in=Subquery(
        #        ChatParticipant.filter(
        #            user__id__in=[user_id, other_user_id], left=False,
        #        ).group_by(
        #            "chat__id", "channel__id",
        #        ).annotate(
        #            user_count=Count("user__id", distinct=True),
        #        ).filter(
        #            user_count=2,
        #        ).values_list("id", flat=True)
        #    )
        #).select_related(
        #    "chat", "chat__photo", "channel", "channel__photo",
        #).order_by("-chat__id", "-channel__id")

        return ChatParticipant.filter(id=0)
