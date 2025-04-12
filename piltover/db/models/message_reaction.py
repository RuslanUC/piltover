from __future__ import annotations

from tortoise import fields, Model

from piltover.db import models


class MessageReaction(Model):
    id: int = fields.BigIntField(pk=True)
    user: models.User = fields.ForeignKeyField("models.User")
    message: models.Message = fields.ForeignKeyField("models.Message")
    reaction: models.Reaction = fields.ForeignKeyField("models.Reaction")

    reaction_id: int

    class Meta:
        unique_together = (
            ("user", "message",),
        )
