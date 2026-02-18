from __future__ import annotations

from tortoise import fields, Model

from piltover.db import models


class MessageReaction(Model):
    id: int = fields.BigIntField(pk=True)
    user: models.User = fields.ForeignKeyField("models.User")
    message: models.MessageContent = fields.ForeignKeyField("models.MessageContent")
    reaction: models.Reaction | None = fields.ForeignKeyField("models.Reaction", null=True, default=None)
    custom_emoji: models.File | None = fields.ForeignKeyField("models.File", null=True, default=None)

    user_id: int
    message_id: int
    reaction_id: int | None
    custom_emoji_id: int | None

    class Meta:
        unique_together = (
            ("user", "message",),
        )
