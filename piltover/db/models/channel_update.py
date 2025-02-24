from __future__ import annotations

from datetime import datetime

from tortoise import fields, Model
from tortoise.expressions import Q

from piltover.db import models
from piltover.db.enums import ChannelUpdateType
from piltover.db.models import Message
from piltover.tl import UpdateChannel, UpdateDeleteChannelMessages, UpdateEditChannelMessage, Long

UpdateTypes = UpdateChannel | UpdateDeleteChannelMessages | UpdateEditChannelMessage


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
            self, user: models.User, users_q: Q | None = None, chats_q: Q | None = None, channels_q: Q | None = None,
    ) -> tuple[UpdateTypes | None, Q | None, Q | None, Q | None]:
        none_ret = None, users_q, chats_q, channels_q

        channels_q |= Q(id=self.channel_id)

        match self.type:
            case ChannelUpdateType.UPDATE_CHANNEL:
                return UpdateChannel(channel_id=self.channel_id), users_q, chats_q, channels_q
            case ChannelUpdateType.NEW_MESSAGE:
                return none_ret
            case ChannelUpdateType.EDIT_MESSAGE:
                message = await Message.get(id=self.related_id, peer__channel__id=self.channel_id)
                users_q, chats_q, channels_q = message.query_users_chats(users_q, chats_q, channels_q)

                return UpdateEditChannelMessage(
                    message=await message.to_tl(user),
                    pts=self.pts,
                    pts_count=1,
                ), users_q, chats_q, channels_q
            case ChannelUpdateType.DELETE_MESSAGES:
                message_ids = [Long.read_bytes(self.extra_data[i * 8:(i + 1) * 8]) for i in range(self.pts_count)]

                return UpdateDeleteChannelMessages(
                    channel_id=self.channel_id,
                    messages=message_ids,
                    pts=self.pts,
                    pts_count=1,
                ), users_q, chats_q, channels_q

        return none_ret
