from __future__ import annotations

from tortoise import Model, fields

from piltover.db import models
from piltover.db.models.utils import NullableFK


class MessageMention(Model):
    id: int = fields.BigIntField(pk=True)
    # TODO: replace with peer?
    user: models.User = fields.ForeignKeyField("models.User")
    chat: models.Chat | None = NullableFK("models.Chat")
    channel: models.Channel | None = NullableFK("models.Channel")
    message: models.MessageContent = fields.ForeignKeyField("models.MessageContent")
    read: bool = fields.BooleanField(default=False)

    user_id: int
    chat_id: int
    channel_id: int
    message_id: int

    class Meta:
        unique_together = (
            ("user", "message"),
        )
