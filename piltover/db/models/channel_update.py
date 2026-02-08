from __future__ import annotations

from datetime import datetime

from tortoise import fields, Model

from piltover.db import models
from piltover.db.enums import ChannelUpdateType
from piltover.tl import UpdateChannel, UpdateDeleteChannelMessages, UpdateEditChannelMessage, Long, \
    UpdateChannelAvailableMessages
from piltover.utils.users_chats_channels import UsersChatsChannels

UpdateTypes = UpdateChannel | UpdateDeleteChannelMessages | UpdateEditChannelMessage | UpdateChannelAvailableMessages


class ChannelUpdate(Model):
    id: int = fields.BigIntField(pk=True)
    type: ChannelUpdateType = fields.IntEnumField(ChannelUpdateType)
    pts: int = fields.BigIntField()
    pts_count: int = fields.IntField(default=0)
    date: datetime = fields.DatetimeField(auto_now_add=True)
    related_id: int = fields.BigIntField(index=True, null=True)
    extra_data: bytes = fields.BinaryField(null=True, default=None)
    channel: models.Channel = fields.ForeignKeyField("models.Channel")

    channel_id: int

    async def to_tl(
            self, user: models.User, ucc: UsersChatsChannels,
    ) -> UpdateTypes | None:
        ucc.add_channel(self.channel_id)

        match self.type:
            case ChannelUpdateType.UPDATE_CHANNEL:
                return UpdateChannel(
                    channel_id=models.Channel.make_id_from(self.channel_id),
                )
            case ChannelUpdateType.NEW_MESSAGE:
                return None
            case ChannelUpdateType.EDIT_MESSAGE:
                message = await models.MessageRef.get(
                    id=self.related_id, peer__channel__id=self.channel_id,
                ).select_related(*models.MessageRef.PREFETCH_FIELDS)
                ucc.add_message(message.content_id)

                return UpdateEditChannelMessage(
                    message=await message.to_tl(user),
                    pts=self.pts,
                    pts_count=1,
                )
            case ChannelUpdateType.DELETE_MESSAGES:
                message_ids = [Long.read_bytes(self.extra_data[i * 8:(i + 1) * 8]) for i in range(self.pts_count)]

                return UpdateDeleteChannelMessages(
                    channel_id=models.Channel.make_id_from(self.channel_id),
                    messages=message_ids,
                    pts=self.pts,
                    pts_count=1,
                )
            case ChannelUpdateType.UPDATE_MIN_AVAILABLE_ID:
                return UpdateChannelAvailableMessages(
                    channel_id=models.Channel.make_id_from(self.channel_id),
                    available_min_id=Long.read_bytes(self.extra_data),
                )

        return None
