from __future__ import annotations

from datetime import datetime

from tortoise import Model, fields

from piltover.db import models
from piltover.tl import ForumTopic, PeerUser


class ChannelForumTopic(Model):
    id: int = fields.BigIntField(primary_key=True)
    channel: models.Channel = fields.ForeignKeyField("models.Channel", related_name="topics")
    message: models.MessageRef = fields.OneToOneField("models.MessageRef")
    topic_id: int = fields.IntField()
    creator: models.User = fields.ForeignKeyField("models.User")
    #creator_as_channel: models.Channel = fields.ForeignKeyField("models.Channel", related_name="created_topics", null=True, default=None)
    closed: bool = fields.BooleanField(default=False)
    hidden: bool = fields.BooleanField(default=False)
    date: datetime = fields.DatetimeField(auto_now_add=True)
    title: str = fields.CharField(max_length=128, db_index=True)
    icon_color: int = fields.IntField()
    # TODO: pinned
    # TODO: icon_emoji_id

    channel_id: int
    message_id: int
    creator_id: int

    class Meta:
        unique_together = (
            ("channel_id", "topic_id"),
        )

    async def to_tl(self, user_id: int) -> ForumTopic:


        return ForumTopic(
            my=self.creator_id == user_id,
            closed=self.closed,
            hidden=self.hidden and self.id == 1,
            id=self.id,
            date=int(self.date.timestamp()),
            title=self.title,
            icon_color=self.icon_color,
            from_id=PeerUser(user_id=self.creator_id),

            icon_emoji_id=None,
            top_message=self.message_id,
            read_inbox_max_id=read_inbox_max_id,
            read_outbox_max_id=read_outbox_max_id,
            unread_count=unread_count,
            unread_mentions_count=unread_mentions_count,
            unread_reactions_count=unread_reactions_count,
            notify_settings=models.PeerNotifySettings.DEFAULT_TL,
            draft=None,

            # TODO: pinned
            pinned=False,
        )
