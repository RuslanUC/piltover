from __future__ import annotations

from datetime import datetime

from tortoise import fields, Model

from piltover.db import models
from piltover.db.enums import ChannelUpdateType
from piltover.tl import UpdateChannel, \
    UpdateDeleteChannelMessages
from piltover.tl.types import User as TLUser, Chat as TLChat, Channel as TLChannel

UpdateTypes = UpdateChannel | UpdateDeleteChannelMessages


class ChannelUpdate(Model):
    id: int = fields.BigIntField(pk=True)
    type: ChannelUpdateType = fields.IntEnumField(ChannelUpdateType)
    pts: int = fields.BigIntField()
    pts_count: int = fields.IntField(default=0)
    date: datetime = fields.DatetimeField(auto_now_add=True)
    related_id: int = fields.BigIntField(index=True, null=True)
    extra_data: bytes = fields.BinaryField(null=True, default=None)
    channel: models.Channel = fields.ForeignKeyField("models.Channel", unique=True)

    channel_id: int

    async def to_tl(
            self, user: models.User, users: dict[int, TLUser] | None = None, chats: dict[int, TLChat] | None = None,
            channels: dict[int, TLChannel] | None = None,
    ) -> UpdateTypes | None:
        if channels is not None and self.channel_id not in channels:
            self.channel = await self.channel
            channels[self.channel.id] = await self.channel.to_tl(user)

        match self.type:
            case ChannelUpdateType.UPDATE_CHANNEL:
                return UpdateChannel(channel_id=self.channel_id)
            case ChannelUpdateType.NEW_MESSAGE:
                return
